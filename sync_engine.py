"""
Core sync engine for DropSync
Adapted from the working eBay sync script
"""
import csv
import io
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import requests

log = logging.getLogger(__name__)


class EbaySyncEngine:
    """Handles syncing between supplier feeds and eBay"""
    
    def __init__(self, ebay_config: dict):
        """
        ebay_config should contain:
        - app_id, dev_id, cert_id, user_token
        - api_url (production or sandbox)
        - site_id (default 0 = US)
        """
        self.config = ebay_config
        self.batch_size = 4  # eBay max
        
    def build_headers(self, call_name: str) -> dict:
        return {
            "X-EBAY-API-SITEID": self.config.get("site_id", "0"),
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": call_name,
            "X-EBAY-API-APP-NAME": self.config["app_id"],
            "X-EBAY-API-DEV-NAME": self.config["dev_id"],
            "X-EBAY-API-CERT-NAME": self.config["cert_id"],
            "Content-Type": "text/xml",
        }
    
    def download_supplier_stock(self, feed_url: str, feed_type: str, 
                                column_mapping: dict = None) -> Dict[str, int]:
        """
        Download and parse supplier CSV.
        Returns {SKU: quantity} where quantity is 0 or 1 (binary mode).
        """
        log.info(f"Downloading supplier feed from {feed_url}")
        resp = requests.get(feed_url, timeout=30)
        resp.raise_for_status()
        
        stock = {}
        
        # Handle different feed types
        if feed_type == "azuregreen":
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                sku = row.get("NUMBER", "").strip()
                qty_raw = row.get("UNITS", "0").strip()
                cant_sell = row.get("CANTSELL", "0").strip()
                
                if not sku:
                    continue
                
                try:
                    qty = int(float(qty_raw))
                except ValueError:
                    qty = 0
                
                # Only respect CANTSELL flag (not DISCONT)
                if cant_sell == "1":
                    qty = 0
                
                # Binary mode: 0 or 1
                stock[sku] = 1 if qty > 0 else 0
        
        elif feed_type == "diecast":
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                sku = row.get("Product ID", "").strip()
                qty_raw = row.get("Product Visible", "0").strip()
                
                if not sku:
                    continue
                
                try:
                    qty = int(qty_raw)
                except ValueError:
                    if qty_raw.lower() in ("yes", "true", "1", "available"):
                        qty = 1
                    else:
                        qty = 0
                
                stock[sku] = 1 if qty > 0 else 0
        
        elif feed_type == "custom" and column_mapping:
            # Custom CSV with user-defined columns
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                sku = row.get(column_mapping.get("sku_column", "SKU"), "").strip()
                qty_raw = row.get(column_mapping.get("quantity_column", "Quantity"), "0").strip()
                
                if not sku:
                    continue
                
                try:
                    qty = int(float(qty_raw))
                except ValueError:
                    qty = 0
                
                stock[sku] = 1 if qty > 0 else 0
        
        log.info(f"Loaded {len(stock)} SKUs from supplier feed")
        return stock
    
    def fetch_ebay_listings(self) -> List[Dict]:
        """Fetch all active eBay listings for this account"""
        all_items = []
        page = 1
        
        # Get listings from past 119 days
        start_time = (datetime.now() - timedelta(days=119)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        log.info("Fetching eBay listings...")
        
        while True:
            items, total_pages, has_more = self._fetch_listings_page(page, start_time, end_time)
            all_items.extend(items)
            
            log.info(f"  Page {page}/{total_pages} — fetched {len(items)} active listings")
            
            if page >= total_pages and not has_more:
                break
            page += 1
            
            # Safety limit
            if page > 500:
                log.warning("Reached 500 page limit")
                break
        
        log.info(f"Total active listings fetched: {len(all_items)}")
        return all_items
    
    def _fetch_listings_page(self, page: int, start_time: str, end_time: str) -> Tuple[List[Dict], int, bool]:
        """Fetch one page of listings using GetSellerList API"""
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetSellerListRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{self.config['user_token']}</eBayAuthToken>
  </RequesterCredentials>
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  <StartTimeFrom>{start_time}</StartTimeFrom>
  <StartTimeTo>{end_time}</StartTimeTo>
  <Pagination>
    <EntriesPerPage>200</EntriesPerPage>
    <PageNumber>{page}</PageNumber>
  </Pagination>
  <GranularityLevel>Fine</GranularityLevel>
</GetSellerListRequest>"""
        
        resp = requests.post(
            self.config.get("api_url", "https://api.ebay.com/ws/api.dll"),
            headers=self.build_headers("GetSellerList"),
            data=xml_body.encode("utf-8"),
            timeout=60,
        )
        resp.raise_for_status()
        
        ns = "urn:ebay:apis:eBLBaseComponents"
        root = ET.fromstring(resp.text)
        
        # Check for errors
        ack = root.findtext(f"{{{ns}}}Ack", "")
        if ack not in ("Success", "Warning"):
            errors = root.findall(f".//{{{ns}}}Errors")
            msgs = []
            for err in errors:
                code = err.findtext(f"{{{ns}}}ErrorCode", "")
                msg = err.findtext(f"{{{ns}}}LongMessage", "") or err.findtext(f"{{{ns}}}ShortMessage", "")
                msgs.append(f"[{code}] {msg}")
            raise RuntimeError(f"GetSellerList failed: {msgs}")
        
        items = []
        for item in root.findall(f".//{{{ns}}}ItemArray/{{{ns}}}Item"):
            item_id = item.findtext(f"{{{ns}}}ItemID", "")
            sku = item.findtext(f"{{{ns}}}SKU", "").strip()
            
            # Only active listings
            status = item.findtext(f"{{{ns}}}SellingStatus/{{{ns}}}ListingStatus", "")
            if status != "Active":
                continue
            
            # Get quantity
            qty_el = item.find(f"{{{ns}}}Quantity")
            qty_sold_el = item.find(f"{{{ns}}}SellingStatus/{{{ns}}}QuantitySold")
            
            qty_total = int(qty_el.text) if qty_el is not None and qty_el.text else 0
            qty_sold = int(qty_sold_el.text) if qty_sold_el is not None and qty_sold_el.text else 0
            qty_available = max(0, qty_total - qty_sold)
            
            if item_id and sku:
                items.append({
                    "item_id": item_id,
                    "sku": sku,
                    "current_qty": qty_available
                })
        
        # Pagination
        pagination_result = root.find(f".//{{{ns}}}PaginationResult")
        total_pages = 1
        has_more = False
        
        if pagination_result is not None:
            total_pages_el = pagination_result.find(f"{{{ns}}}TotalNumberOfPages")
            total_pages = int(total_pages_el.text) if total_pages_el is not None else 1
        
        has_more_el = root.find(f".//{{{ns}}}HasMoreItems")
        has_more = has_more_el is not None and has_more_el.text == "true"
        
        return items, total_pages, has_more
    
    def update_ebay_quantities(self, updates: List[Dict]) -> Tuple[int, int]:
        """
        Update quantities on eBay in batches.
        Returns (success_count, failed_count)
        """
        total_success = 0
        total_failed = 0
        
        for i in range(0, len(updates), self.batch_size):
            batch = updates[i : i + self.batch_size]
            
            try:
                success = self._update_batch(batch)
                total_success += success
                if success < len(batch):
                    total_failed += len(batch) - success
            except Exception as e:
                log.error(f"Batch update failed: {e}")
                total_failed += len(batch)
        
        return total_success, total_failed
    
    def _update_batch(self, batch: List[Dict]) -> int:
        """Update one batch of items"""
        inventory_items_xml = ""
        for item in batch:
            inventory_items_xml += f"""
  <InventoryStatus>
    <ItemID>{item['item_id']}</ItemID>
    <Quantity>{item['new_qty']}</Quantity>
  </InventoryStatus>"""
        
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<ReviseInventoryStatusRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{self.config['user_token']}</eBayAuthToken>
  </RequesterCredentials>
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  {inventory_items_xml}
</ReviseInventoryStatusRequest>"""
        
        resp = requests.post(
            self.config.get("api_url", "https://api.ebay.com/ws/api.dll"),
            headers=self.build_headers("ReviseInventoryStatus"),
            data=xml_body.encode("utf-8"),
            timeout=60,
        )
        resp.raise_for_status()
        
        ns = "urn:ebay:apis:eBLBaseComponents"
        root = ET.fromstring(resp.text)
        ack = root.findtext(f"{{{ns}}}Ack", "")
        
        if ack in ("Success", "Warning"):
            updated_items = root.findall(f".//{{{ns}}}InventoryStatus")
            return len(updated_items)
        
        return 0
    
    def run_sync(self, feed_url: str, feed_type: str, 
                 column_mapping: dict = None) -> dict:
        """
        Main sync operation.
        Returns summary dict with stats.
        """
        start_time = datetime.now()
        
        try:
            # 1. Download supplier stock
            supplier_stock = self.download_supplier_stock(feed_url, feed_type, column_mapping)
            
            # 2. Fetch eBay listings
            ebay_listings = self.fetch_ebay_listings()
            
            # 3. Find items needing update
            updates_needed = []
            unmatched_skus = []
            
            for listing in ebay_listings:
                sku = listing["sku"]
                if sku not in supplier_stock:
                    unmatched_skus.append(sku)
                    continue
                
                new_qty = supplier_stock[sku]
                if new_qty != listing["current_qty"]:
                    updates_needed.append({
                        "item_id": listing["item_id"],
                        "sku": sku,
                        "old_qty": listing["current_qty"],
                        "new_qty": new_qty,
                    })
            
            log.info(f"Listings needing update: {len(updates_needed)}")
            log.info(f"Listings with no SKU match: {len(unmatched_skus)}")
            
            # 4. Update eBay
            items_updated = 0
            items_failed = 0
            
            if updates_needed:
                items_updated, items_failed = self.update_ebay_quantities(updates_needed)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return {
                "status": "completed",
                "total_listings_checked": len(ebay_listings),
                "items_updated": items_updated,
                "items_failed": items_failed,
                "items_out_of_stock": sum(1 for u in updates_needed if u["new_qty"] == 0),
                "unmatched_skus": len(unmatched_skus),
                "duration_seconds": duration,
                "error_message": None,
            }
        
        except Exception as e:
            log.exception("Sync failed")
            duration = (datetime.now() - start_time).total_seconds()
            
            return {
                "status": "failed",
                "total_listings_checked": 0,
                "items_updated": 0,
                "items_failed": 0,
                "items_out_of_stock": 0,
                "unmatched_skus": 0,
                "duration_seconds": duration,
                "error_message": str(e),
            }
