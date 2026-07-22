import React from 'react';
import ReactDOM from 'react-dom/client';
// Self-hosted font (bundled; offline-safe).
import '@fontsource-variable/inter';
import App from './App';
import './styles/federation.css';
import './styles/app.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
