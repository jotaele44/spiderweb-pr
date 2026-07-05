import { useState, useEffect, useCallback } from 'react';
import { federation } from '@/api/federationClient';
import { Github, GitCommit, GitPullRequest, CircleDot, RefreshCw, ChevronDown, ExternalLink, AlertCircle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

const TABS = [
  { id: 'commits', label: 'Commits', icon: GitCommit },
  { id: 'prs', label: 'PRs', icon: GitPullRequest },
  { id: 'issues', label: 'Issues', icon: CircleDot },
];

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function StateTag({ state, merged_at }) {
  if (merged_at) return <span className="font-mono text-xs px-1.5 py-0.5 rounded border border-purple-500/40 text-purple-400 bg-purple-500/10">merged</span>;
  if (state === 'open') return <span className="font-mono text-xs px-1.5 py-0.5 rounded border border-green-500/40 text-green-400 bg-green-500/10">open</span>;
  return <span className="font-mono text-xs px-1.5 py-0.5 rounded border border-border/50 text-muted-foreground bg-muted/20">closed</span>;
}

export default function GitHubPanel({ collapsed, onToggle }) {
  const [repos, setRepos] = useState([]);
  const [selectedRepo, setSelectedRepo] = useState(null);
  const [activity, setActivity] = useState(null);
  const [activeTab, setActiveTab] = useState('commits');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showRepoList, setShowRepoList] = useState(false);

  const fetchRepos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await federation.functions.invoke('githubActivity', {});
      setRepos(res.data.repos || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchActivity = useCallback(async (repo) => {
    if (!repo) return;
    setLoading(true);
    setError(null);
    setActivity(null);
    try {
      const res = await federation.functions.invoke('githubActivity', { owner: repo.owner, repo: repo.name });
      setActivity(res.data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!collapsed) fetchRepos();
  }, [collapsed, fetchRepos]);

  const handleSelectRepo = (repo) => {
    setSelectedRepo(repo);
    setShowRepoList(false);
    fetchActivity(repo);
  };

  const items = activity
    ? activeTab === 'commits'
      ? activity.commits
      : activeTab === 'prs'
      ? activity.pullRequests
      : activity.issues
    : [];

  return (
    <div className={cn('panel-glass border-t flex flex-col transition-all duration-300 shrink-0', collapsed ? 'h-8' : 'h-64')}>
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border/50 shrink-0 cursor-pointer" onClick={onToggle}>
        <Github className="w-3.5 h-3.5 text-primary" />
        <span className="font-mono text-xs text-primary font-semibold tracking-wider flex-1">GITHUB ACTIVITY</span>
        {selectedRepo && !collapsed && (
          <span className="font-mono text-xs text-muted-foreground">{selectedRepo.full_name}</span>
        )}
        {loading && <Loader2 className="w-3 h-3 text-muted-foreground animate-spin" />}
        <ChevronDown className={cn('w-3.5 h-3.5 text-muted-foreground transition-transform', !collapsed && 'rotate-180')} />
      </div>

      {!collapsed && (
        <div className="flex flex-col flex-1 min-h-0">
          {/* Repo selector */}
          <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border/30 shrink-0">
            <div className="relative flex-1">
              <button
                onClick={() => setShowRepoList(!showRepoList)}
                className="w-full flex items-center gap-2 px-2 py-1 rounded border border-border/50 hover:border-primary/40 bg-secondary/30 font-mono text-xs text-foreground transition-colors"
              >
                <span className="flex-1 text-left truncate">
                  {selectedRepo ? selectedRepo.full_name : 'Select repository...'}
                </span>
                <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
              </button>
              {showRepoList && repos.length > 0 && (
                <div className="absolute top-full left-0 right-0 z-50 mt-0.5 panel-glass border border-border rounded max-h-48 overflow-y-auto">
                  {repos.map((r) => (
                    <button
                      key={r.id}
                      onClick={() => handleSelectRepo(r)}
                      className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-primary/5 text-left transition-colors"
                    >
                      <span className="font-mono text-xs text-foreground truncate flex-1">{r.full_name}</span>
                      {r.language && <span className="font-mono text-xs text-muted-foreground/60 shrink-0">{r.language}</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {selectedRepo && (
              <button
                onClick={() => fetchActivity(selectedRepo)}
                className="text-muted-foreground hover:text-primary transition-colors"
                title="Refresh"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {error && (
            <div className="px-3 py-2 flex items-center gap-2 text-destructive font-mono text-xs">
              <AlertCircle className="w-3 h-3 shrink-0" />
              {error}
            </div>
          )}

          {activity && (
            <>
              {/* Tabs */}
              <div className="flex border-b border-border/30 shrink-0">
                {TABS.map((tab) => {
                  const Icon = tab.icon;
                  const count = tab.id === 'commits' ? activity.commits?.length : tab.id === 'prs' ? activity.pullRequests?.length : activity.issues?.length;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={cn(
                        'flex-1 flex items-center justify-center gap-1 py-1 font-mono text-xs transition-all',
                        activeTab === tab.id ? 'text-primary border-b-2 border-primary bg-primary/5' : 'text-muted-foreground hover:text-foreground'
                      )}
                    >
                      <Icon className="w-3 h-3" />
                      {tab.label}
                      <span className="text-muted-foreground/50">({count})</span>
                    </button>
                  );
                })}
              </div>

              {/* Items list */}
              <div className="flex-1 overflow-y-auto min-h-0">
                {items.map((item, i) => (
                  <div key={i} className="flex items-start gap-2 px-3 py-1.5 border-b border-border/20 hover:bg-primary/5 transition-colors group">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {activeTab !== 'commits' && <StateTag state={item.state} merged_at={item.merged_at} />}
                        {activeTab !== 'commits' && <span className="font-mono text-xs text-muted-foreground/50">#{item.number}</span>}
                        {activeTab === 'commits' && <span className="font-mono text-xs text-primary/70">{item.sha}</span>}
                        <p className="font-mono text-xs text-foreground/90 truncate">{item.message || item.title}</p>
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="font-mono text-xs text-muted-foreground/50">{item.author || item.author}</span>
                        <span className="font-mono text-xs text-muted-foreground/30">{timeAgo(item.date || item.updated_at)}</span>
                      </div>
                    </div>
                    <a href={item.url} target="_blank" rel="noopener noreferrer" className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-primary transition-all shrink-0">
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                ))}
              </div>
            </>
          )}

          {!activity && !loading && !error && (
            <div className="flex-1 flex items-center justify-center">
              <p className="font-mono text-xs text-muted-foreground/40">← Select a repository to view activity</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}