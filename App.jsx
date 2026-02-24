import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import './App.css';

// API client
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiClient {
  constructor() {
    this.token = localStorage.getItem('token');
  }

  setToken(token) {
    this.token = token;
    localStorage.setItem('token', token);
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem('token');
  }

  async request(endpoint, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      this.clearToken();
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'Request failed');
    }

    return data;
  }

  async login(email, password) {
    const data = await this.request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async register(email, password, fullName) {
    const data = await this.request('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async getMe() {
    return this.request('/api/auth/me');
  }

  async getAccounts() {
    return this.request('/api/accounts');
  }

  async createAccount(accountData) {
    return this.request('/api/accounts', {
      method: 'POST',
      body: JSON.stringify(accountData),
    });
  }

  async getFeeds() {
    return this.request('/api/feeds');
  }

  async createFeed(feedData) {
    return this.request('/api/feeds', {
      method: 'POST',
      body: JSON.stringify(feedData),
    });
  }

  async triggerSync(accountId, feedId) {
    return this.request('/api/sync/trigger', {
      method: 'POST',
      body: JSON.stringify({ account_id: accountId, feed_id: feedId }),
    });
  }

  async getSyncJobs(accountId) {
    const params = accountId ? `?account_id=${accountId}` : '';
    return this.request(`/api/sync/jobs${params}`);
  }

  async getDashboardStats() {
    return this.request('/api/dashboard/stats');
  }
}

const api = new ApiClient();

// Auth Context
const AuthContext = React.createContext(null);

function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (api.token) {
      api.getMe()
        .then(setUser)
        .catch(() => api.clearToken())
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email, password) => {
    await api.login(email, password);
    const userData = await api.getMe();
    setUser(userData);
  };

  const register = async (email, password, fullName) => {
    await api.register(email, password, fullName);
    const userData = await api.getMe();
    setUser(userData);
  };

  const logout = () => {
    api.clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

function useAuth() {
  return React.useContext(AuthContext);
}

// Login Page
function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isRegister, setIsRegister] = useState(false);
  const [fullName, setFullName] = useState('');
  const { login, register } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    try {
      if (isRegister) {
        await register(email, password, fullName);
      } else {
        await login(email, password);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-container">
        <h1>DropSync</h1>
        <p className="tagline">Automated eBay Inventory Management</p>
        
        <form onSubmit={handleSubmit} className="auth-form">
          <h2>{isRegister ? 'Create Account' : 'Sign In'}</h2>
          
          {error && <div className="error-message">{error}</div>}
          
          {isRegister && (
            <input
              type="text"
              placeholder="Full Name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          )}
          
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          
          <button type="submit" className="btn-primary">
            {isRegister ? 'Sign Up' : 'Sign In'}
          </button>
          
          <p className="toggle-auth">
            {isRegister ? 'Already have an account?' : "Don't have an account?"}
            <button
              type="button"
              className="link-button"
              onClick={() => setIsRegister(!isRegister)}
            >
              {isRegister ? 'Sign In' : 'Sign Up'}
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}

// Dashboard Page
function DashboardPage() {
  const [stats, setStats] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [feeds, setFeeds] = useState([]);
  const [jobs, setJobs] = useState([]);
  const { user, logout } = useAuth();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statsData, accountsData, feedsData, jobsData] = await Promise.all([
        api.getDashboardStats(),
        api.getAccounts(),
        api.getFeeds(),
        api.getSyncJobs(),
      ]);
      
      setStats(statsData);
      setAccounts(accountsData);
      setFeeds(feedsData);
      setJobs(jobsData);
    } catch (err) {
      console.error('Failed to load data:', err);
    }
  };

  const handleSync = async (accountId, feedId) => {
    try {
      await api.triggerSync(accountId, feedId);
      alert('Sync triggered! Check the jobs tab for progress.');
      setTimeout(loadData, 2000);
    } catch (err) {
      alert('Sync failed: ' + err.message);
    }
  };

  return (
    <div className="dashboard">
      <nav className="navbar">
        <h1>DropSync</h1>
        <div className="nav-right">
          <span>{user?.email}</span>
          <span className="plan-badge">{user?.plan}</span>
          <button onClick={logout} className="btn-secondary">Logout</button>
        </div>
      </nav>

      <div className="dashboard-content">
        <div className="stats-grid">
          <div className="stat-card">
            <h3>{stats?.total_accounts || 0}</h3>
            <p>eBay Accounts</p>
          </div>
          <div className="stat-card">
            <h3>{stats?.total_feeds || 0}</h3>
            <p>Supplier Feeds</p>
          </div>
          <div className="stat-card">
            <h3>{stats?.last_sync_items_updated || 0}</h3>
            <p>Last Sync Updated</p>
          </div>
          <div className="stat-card">
            <h3>{stats?.last_sync_status || 'Never'}</h3>
            <p>Last Sync Status</p>
          </div>
        </div>

        <div className="section">
          <div className="section-header">
            <h2>eBay Accounts</h2>
            <button 
              onClick={() => window.location.href = '/accounts/new'} 
              className="btn-primary"
            >
              + Add Account
            </button>
          </div>
          
          {accounts.length === 0 ? (
            <p className="empty-state">No eBay accounts connected yet.</p>
          ) : (
            <div className="accounts-list">
              {accounts.map(account => (
                <div key={account.id} className="account-card">
                  <h3>{account.store_name}</h3>
                  <p>Sync: {account.sync_frequency}</p>
                  <p>Last: {account.last_sync_at ? new Date(account.last_sync_at).toLocaleString() : 'Never'}</p>
                  
                  {feeds.length > 0 && (
                    <button
                      onClick={() => handleSync(account.id, feeds[0].id)}
                      className="btn-primary btn-sm"
                    >
                      Sync Now
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="section">
          <div className="section-header">
            <h2>Supplier Feeds</h2>
            <button 
              onClick={() => window.location.href = '/feeds/new'} 
              className="btn-primary"
            >
              + Add Feed
            </button>
          </div>
          
          {feeds.length === 0 ? (
            <p className="empty-state">No supplier feeds added yet.</p>
          ) : (
            <div className="feeds-list">
              {feeds.map(feed => (
                <div key={feed.id} className="feed-card">
                  <h3>{feed.name}</h3>
                  <p>Type: {feed.feed_type}</p>
                  <p>SKUs: {feed.total_skus || 'Not fetched yet'}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="section">
          <h2>Recent Sync Jobs</h2>
          
          {jobs.length === 0 ? (
            <p className="empty-state">No sync jobs yet. Click "Sync Now" to start.</p>
          ) : (
            <table className="jobs-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Status</th>
                  <th>Checked</th>
                  <th>Updated</th>
                  <th>Failed</th>
                  <th>Duration</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map(job => (
                  <tr key={job.id}>
                    <td>{new Date(job.started_at).toLocaleString()}</td>
                    <td>
                      <span className={`status-badge status-${job.status}`}>
                        {job.status}
                      </span>
                    </td>
                    <td>{job.total_listings_checked}</td>
                    <td>{job.items_updated}</td>
                    <td>{job.items_failed}</td>
                    <td>{job.duration_seconds?.toFixed(1)}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

// Add Account Form
function AddAccountPage() {
  const [formData, setFormData] = useState({
    store_name: '',
    app_id: '',
    dev_id: '',
    cert_id: '',
    user_token: '',
    sync_frequency: 'daily',
    sync_time: '06:00',
  });
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    try {
      await api.createAccount(formData);
      window.location.href = '/';
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="form-page">
      <div className="form-container">
        <h2>Connect eBay Account</h2>
        
        {error && <div className="error-message">{error}</div>}
        
        <form onSubmit={handleSubmit}>
          <label>
            Store Name
            <input
              type="text"
              value={formData.store_name}
              onChange={(e) => setFormData({...formData, store_name: e.target.value})}
              required
            />
          </label>
          
          <label>
            eBay App ID
            <input
              type="text"
              value={formData.app_id}
              onChange={(e) => setFormData({...formData, app_id: e.target.value})}
              required
            />
          </label>
          
          <label>
            eBay Dev ID
            <input
              type="text"
              value={formData.dev_id}
              onChange={(e) => setFormData({...formData, dev_id: e.target.value})}
              required
            />
          </label>
          
          <label>
            eBay Cert ID
            <input
              type="text"
              value={formData.cert_id}
              onChange={(e) => setFormData({...formData, cert_id: e.target.value})}
              required
            />
          </label>
          
          <label>
            eBay User Token
            <textarea
              value={formData.user_token}
              onChange={(e) => setFormData({...formData, user_token: e.target.value})}
              rows={4}
              required
            />
          </label>
          
          <label>
            Sync Frequency
            <select
              value={formData.sync_frequency}
              onChange={(e) => setFormData({...formData, sync_frequency: e.target.value})}
            >
              <option value="manual">Manual Only</option>
              <option value="daily">Daily</option>
              <option value="hourly">Hourly</option>
            </select>
          </label>
          
          <label>
            Sync Time (for daily sync)
            <input
              type="time"
              value={formData.sync_time}
              onChange={(e) => setFormData({...formData, sync_time: e.target.value})}
            />
          </label>
          
          <div className="button-group">
            <button type="submit" className="btn-primary">Connect Account</button>
            <button 
              type="button" 
              onClick={() => window.location.href = '/'} 
              className="btn-secondary"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Add Feed Form
function AddFeedPage() {
  const [formData, setFormData] = useState({
    name: '',
    feed_url: '',
    feed_type: 'azuregreen',
    sku_column: 'NUMBER',
    quantity_column: 'UNITS',
  });
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    try {
      await api.createFeed(formData);
      window.location.href = '/';
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="form-page">
      <div className="form-container">
        <h2>Add Supplier Feed</h2>
        
        {error && <div className="error-message">{error}</div>}
        
        <form onSubmit={handleSubmit}>
          <label>
            Feed Name
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({...formData, name: e.target.value})}
              placeholder="e.g., AzureGreen"
              required
            />
          </label>
          
          <label>
            Feed URL
            <input
              type="url"
              value={formData.feed_url}
              onChange={(e) => setFormData({...formData, feed_url: e.target.value})}
              placeholder="https://example.com/feed.csv"
              required
            />
          </label>
          
          <label>
            Feed Type
            <select
              value={formData.feed_type}
              onChange={(e) => setFormData({...formData, feed_type: e.target.value})}
            >
              <option value="azuregreen">AzureGreen</option>
              <option value="diecast">Diecast Dropshipper</option>
              <option value="custom">Custom CSV</option>
            </select>
          </label>
          
          {formData.feed_type === 'custom' && (
            <>
              <label>
                SKU Column Name
                <input
                  type="text"
                  value={formData.sku_column}
                  onChange={(e) => setFormData({...formData, sku_column: e.target.value})}
                  required
                />
              </label>
              
              <label>
                Quantity Column Name
                <input
                  type="text"
                  value={formData.quantity_column}
                  onChange={(e) => setFormData({...formData, quantity_column: e.target.value})}
                  required
                />
              </label>
            </>
          )}
          
          <div className="button-group">
            <button type="submit" className="btn-primary">Add Feed</button>
            <button 
              type="button" 
              onClick={() => window.location.href = '/'} 
              className="btn-secondary"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Protected Route
function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  return user ? children : <Navigate to="/login" />;
}

// Main App
function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          } />
          <Route path="/accounts/new" element={
            <ProtectedRoute>
              <AddAccountPage />
            </ProtectedRoute>
          } />
          <Route path="/feeds/new" element={
            <ProtectedRoute>
              <AddFeedPage />
            </ProtectedRoute>
          } />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
