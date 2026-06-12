import { Routes, Route, NavLink, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Comparator from './pages/Comparator';
import SqlAnalysis from './pages/SqlAnalysis';
import WaitEvents from './pages/WaitEvents';
import Recommendations from './pages/Recommendations';

const navItems = [
  { path: '/', label: 'Dashboard', icon: '◉' },
  { path: '/compare', label: 'AWR Comparator', icon: '⟺' },
  { path: '/sql', label: 'SQL Analysis', icon: '⟐' },
  { path: '/waits', label: 'Wait Events', icon: '◎' },
  { path: '/recommendations', label: 'Recommendations', icon: '✦' },
];

export default function App() {
  const location = useLocation();

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-gradient-to-b from-dark-800 to-dark-900 border-r border-dark-500 flex flex-col">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-dark-500">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent-amber to-amber-600 flex items-center justify-center text-black font-bold text-sm">
              OV
            </div>
            <div>
              <div className="font-bold text-sm text-text-primary">OraVision</div>
              <div className="text-[0.6rem] text-text-muted uppercase tracking-widest">AWR Pro v2.0</div>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                `nav-link ${isActive ? 'active' : ''}`
              }
            >
              <span className="text-lg opacity-70">{item.icon}</span>
              <span>{item.label}</span>
              {item.path === '/compare' && (
                <span className="ml-auto text-[0.6rem] bg-accent-amber/20 text-accent-amber px-1.5 py-0.5 rounded font-bold">
                  NEW
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-dark-500">
          <div className="text-[0.6rem] text-text-muted">
            Oracle AWR Performance Intelligence
          </div>
          <div className="text-[0.6rem] text-dark-400 mt-1">
            v2.0 — React + FastAPI
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto bg-dark-900">
        {/* Top Header */}
        <header className="sticky top-0 z-10 bg-dark-900/80 backdrop-blur-sm border-b border-dark-500 px-6 py-3 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-text-primary">
              {navItems.find(n => {
                if (n.path === '/') return location.pathname === '/';
                return location.pathname.startsWith(n.path);
              })?.label || 'Dashboard'}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-text-muted font-mono">AWR Data Mode</span>
            <div className="w-2 h-2 rounded-full bg-accent-green animate-pulse" title="API Connected"></div>
          </div>
        </header>

        {/* Page Content */}
        <div className="p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/compare" element={<Comparator />} />
            <Route path="/sql" element={<SqlAnalysis />} />
            <Route path="/waits" element={<WaitEvents />} />
            <Route path="/recommendations" element={<Recommendations />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
