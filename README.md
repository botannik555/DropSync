# DropSync - eBay Inventory Automation SaaS

Complete MVP for automated eBay inventory management.

## Features

✅ User Authentication (JWT)
✅ eBay Account Management
✅ Supplier Feed Integration (AzureGreen, Diecast, Custom CSV)
✅ Manual & Scheduled Syncs
✅ Real-time Dashboard
✅ Sync Job History
✅ Binary Quantity Mode (0 or 1)
✅ Multi-Account Support
✅ Responsive Design
✅ Production Ready

## Tech Stack

**Backend:**
- FastAPI (Python)
- SQLAlchemy ORM
- PostgreSQL / SQLite
- JWT Authentication
- APScheduler for cron jobs

**Frontend:**
- React 18
- React Router
- Vite
- Modern CSS

## Quick Start

### Backend
```bash
cd backend/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Frontend
```bash
cd frontend/
npm install
npm run dev
```

See `SETUP_GUIDE.txt` for complete instructions.

## Project Structure

```
dropsync_mvp/
├── backend/
│   ├── main.py           # FastAPI app & API endpoints
│   ├── models.py         # Database models
│   ├── sync_engine.py    # Core sync logic
│   └── requirements.txt  # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx       # Main React app
│   │   ├── App.css       # Styling
│   │   └── main.jsx      # Entry point
│   ├── package.json      # Node dependencies
│   └── vite.config.js    # Vite config
└── SETUP_GUIDE.txt       # Deployment guide
```

## API Endpoints

### Auth
- POST `/api/auth/register` - Create account
- POST `/api/auth/login` - Login
- GET `/api/auth/me` - Get current user

### Accounts
- GET `/api/accounts` - List eBay accounts
- POST `/api/accounts` - Connect eBay account
- DELETE `/api/accounts/{id}` - Remove account

### Feeds
- GET `/api/feeds` - List supplier feeds
- POST `/api/feeds` - Add supplier feed
- DELETE `/api/feeds/{id}` - Remove feed

### Sync
- POST `/api/sync/trigger` - Trigger manual sync
- GET `/api/sync/jobs` - List sync jobs
- GET `/api/sync/jobs/{id}` - Get job details

### Dashboard
- GET `/api/dashboard/stats` - Get dashboard stats

## Environment Variables

### Backend (.env)
```env
DATABASE_URL=sqlite:///./dropsync.db
SECRET_KEY=your-secret-key-here
STRIPE_SECRET_KEY=sk_test_...
```

### Frontend (.env.local)
```env
VITE_API_URL=http://localhost:8000
```

## Deployment

See `SETUP_GUIDE.txt` for complete deployment instructions.

**Recommended:**
- Backend: Railway.app (free tier)
- Frontend: Vercel (free)
- Database: Railway PostgreSQL

## Pricing Tiers

- **Starter** - $29/month
  - 1 eBay account
  - 10,000 listings
  - 2 supplier feeds

- **Professional** - $79/month
  - 3 eBay accounts
  - 50,000 listings
  - 5 supplier feeds

- **Enterprise** - $199/month
  - Unlimited accounts
  - Unlimited listings
  - Unlimited feeds

## License

MIT License - Feel free to use this for your own SaaS!

## Support

For issues or questions, see SETUP_GUIDE.txt

---

Built with ❤️ for eBay dropshippers
