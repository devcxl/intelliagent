import { useState } from 'react';
import { Plus, Trash2, Play } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

interface SidebarSession {
  id: string;
  title: string;
  task: string;
  logs: any[];
  status: 'idle' | 'running' | 'completed' | 'error';
  createdAt: string;
  updatedAt: string;
}

interface SidebarProps {
  sessions: SidebarSession[];
  currentSessionId: string | null;
  onCreateSession: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

export function Sidebar({
  sessions,
  currentSessionId,
  onCreateSession,
  onSelectSession,
  onDeleteSession,
}: SidebarProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes} 分钟前`;
    if (hours < 24) return `${hours} 小时前`;
    if (days < 7) return `${days} 天前`;
    return date.toLocaleDateString('zh-CN');
  };

  const getStatusBadge = (status: SidebarSession['status']) => {
    switch (status) {
      case 'running':
        return <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />;
      case 'completed':
        return <span className="w-2 h-2 bg-green-500 rounded-full" />;
      case 'error':
        return <span className="w-2 h-2 bg-red-500 rounded-full" />;
      default:
        return <span className="w-2 h-2 bg-gray-400 rounded-full" />;
    }
  };

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-card to-muted/20 border-r">
      <div className="p-3 border-b bg-card/80 backdrop-blur-sm">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-bold gradient-text">会话管理</h2>
          <Button size="icon" variant="ghost" onClick={onCreateSession} className="hover:bg-primary/10 hover:text-primary h-7 w-7">
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="text-xs text-muted-foreground font-medium">
          共 {sessions.length} 个会话
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1.5">
          {sessions.map((session) => (
            <Card
              key={session.id}
              className={cn(
                'p-3 cursor-pointer transition-all duration-200 hover:shadow-md',
                currentSessionId === session.id
                  ? 'bg-primary/5 border-primary/30 shadow-sm'
                  : 'hover:bg-accent/70'
              )}
              onMouseEnter={() => setHoveredId(session.id)}
              onMouseLeave={() => setHoveredId(null)}
              onClick={() => onSelectSession(session.id)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <div className="p-0.5 rounded-full bg-background/50">
                      {getStatusBadge(session.status)}
                    </div>
                    <h3 className="text-xs font-semibold truncate">
                      {session.title}
                    </h3>
                  </div>
                  <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                    {session.task || '无任务描述'}
                  </p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <p className="text-xs text-muted-foreground/70 font-medium">
                      {formatDate(session.updatedAt)}
                    </p>
                  </div>
                </div>
                
                {hoveredId === session.id && session.id !== currentSessionId && (
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-6 w-6 hover:bg-primary/10 hover:text-primary"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectSession(session.id);
                      }}
                    >
                      <Play className="h-3 w-3" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-6 w-6 hover:bg-destructive/10 hover:text-destructive"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (window.confirm('确定要删除这个会话吗？')) {
                          onDeleteSession(session.id);
                        }
                      }}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
