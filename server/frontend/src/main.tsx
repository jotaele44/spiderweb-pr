import React from 'react';
import ReactDOM from 'react-dom/client';
// Self-hosted font (bundled; offline-safe).
import '@fontsource-variable/inter';
import App from './App';
// Shared federation design layer (single-sourced from @pr-federation/react),
// then this app's own styles.
import '@pr-federation/react/styles.css';
import './styles/app.css';

document.documentElement.dataset.repo = 'spiderweb-pr';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
