import { useState, useRef } from 'react';
import { Upload, Wifi, WifiOff, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function TopBar({ connectionStatus, onFileUpload, onRefreshConnection, isUploading }) {
  const fileRef = useRef();
  const [dragOver, setDragOver] = useState(false);

  const handleFile = (file) => {
    if (!file) return;
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['geojson', 'json', 'csv', 'zip'].includes(ext)) {
      alert('Supported formats: .geojson, .json, .csv, .zip (Shapefile)');
      return;
    }
    onFileUpload(file);
  };

  return (
    <header className="h-12 panel-glass border-b flex items-center px-4 gap-4 z-50 relative shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 mr-2">
        <div className="w-6 h-6 rounded border border-primary/50 flex items-center justify-center glow-cyan">
          <div className="w-2 h-2 bg-primary rounded-sm" />
        </div>
        <span className="font-mono text-sm font-semibold text-primary tracking-widest">GEOMIND</span>
        <span className="text-muted-foreground font-mono text-xs">v0.1</span>
      </div>

      <div className="h-4 w-px bg-border" />

      {/* Upload */}
      <button
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }}
        disabled={isUploading}
        className={cn(
          'flex items-center gap-2 px-3 py-1 rounded text-xs font-mono border transition-all',
          dragOver
            ? 'border-primary text-primary bg-primary/10'
            : 'border-border text-muted-foreground hover:border-primary/50 hover:text-primary',
          isUploading && 'opacity-50 cursor-not-allowed'
        )}
      >
        {isUploading ? (
          <RefreshCw className="w-3 h-3 animate-spin" />
        ) : (
          <Upload className="w-3 h-3" />
        )}
        {isUploading ? 'Uploading...' : 'Load Geodata'}
        <span className="text-muted-foreground/50">.geojson .csv .zip</span>
      </button>
      <input
        ref={fileRef}
        type="file"
        accept=".geojson,.json,.csv,.zip"
        className="hidden"
        onChange={(e) => handleFile(e.target.files[0])}
      />

      <div className="flex-1" />

      {/* Connection status */}
      <button
        onClick={onRefreshConnection}
        className="flex items-center gap-2 px-3 py-1 rounded border border-border hover:border-primary/40 transition-all"
      >
        {connectionStatus.connected ? (
          <Wifi className="w-3 h-3 text-green-400" />
        ) : (
          <WifiOff className="w-3 h-3 text-destructive" />
        )}
        <span className={cn('font-mono text-xs', connectionStatus.connected ? 'text-green-400' : 'text-destructive')}>
          {connectionStatus.connected ? 'CONNECTED' : 'OFFLINE'}
        </span>
        <span className="font-mono text-xs text-muted-foreground">localhost:8000</span>
        {connectionStatus.lastChecked && (
          <span className="font-mono text-xs text-muted-foreground/50">
            {new Date(connectionStatus.lastChecked).toLocaleTimeString()}
          </span>
        )}
      </button>
    </header>
  );
}