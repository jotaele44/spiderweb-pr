import React from 'react';
import ReactDOM from 'react-dom/client';
import '@fontsource-variable/inter';
import 'maplibre-gl/dist/maplibre-gl.css';
import '@pr-federation/react/styles.css';
import './styles/app.css';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
