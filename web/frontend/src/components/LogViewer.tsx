import { Brain, Wrench, Eye, CheckCircle2, AlertCircle, Info } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { LogEntry } from '@/types';

interface LogViewerProps {
  logs: LogEntry[];
}

export function LogViewer({ logs }: LogViewerProps) {
  const formatTimestamp = (isoString?: string) => {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const getLogStyle = (type: LogEntry['type']) => {
    switch (type) {
      case 'thought':
        return 'log-thought bg-blue-50/80 border-blue-300 text-blue-900 hover-lift dark:border-blue-400';
      case 'action':
        return 'log-action bg-amber-50/80 border-amber-300 text-amber-900 hover-lift dark:border-amber-400';
      case 'observation':
        return 'log-observation bg-emerald-50/80 border-emerald-300 text-emerald-900 hover-lift dark:border-emerald-400';
      case 'answer':
        return 'log-answer bg-violet-50/80 border-violet-300 text-violet-900 hover-lift dark:border-violet-400';
      case 'error':
        return 'log-error bg-red-50/80 border-red-300 text-red-900 hover-lift dark:border-red-400';
      default:
        return 'log-default bg-slate-50/80 border-slate-300 text-slate-900 hover-lift dark:border-slate-400';
    }
  };

  const getIcon = (type: LogEntry['type']) => {
    switch (type) {
      case 'thought':
        return <Brain className="h-4 w-4" />;
      case 'action':
        return <Wrench className="h-4 w-4" />;
      case 'observation':
        return <Eye className="h-4 w-4" />;
      case 'answer':
        return <CheckCircle2 className="h-4 w-4" />;
      case 'error':
        return <AlertCircle className="h-4 w-4" />;
      default:
        return <Info className="h-4 w-4" />;
    }
  };

  const formatContent = (entry: LogEntry) => {
    const { type, data } = entry;

    switch (type) {
      case 'thought':
        return (
          <div className="space-y-1.5">
            <p className="whitespace-pre-wrap">{data.reasoning}</p>
            {data.is_complete && (
              <Badge variant="default">已完成</Badge>
            )}
          </div>
        );
      case 'action':
        return (
          <div className="space-y-1.5">
            <div className="font-mono text-sm bg-white/50 p-2 rounded">
              <span className="font-bold">{data.tool}</span>
              {data.args && Object.keys(data.args).length > 0 && (
                <pre className="mt-1 text-xs overflow-x-auto">
                  {JSON.stringify(data.args, null, 2)}
                </pre>
              )}
            </div>
          </div>
        );
      case 'observation':
        return (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              {data.status === 'success' ? (
                <Badge variant="default">成功</Badge>
              ) : (
                <Badge variant="destructive">失败</Badge>
              )}
              {data.execution_time && (
                <span className="text-sm text-muted-foreground">
                  耗时: {data.execution_time.toFixed(2)}s
                </span>
              )}
            </div>
            {data.error && (
              <div className="text-sm text-destructive bg-destructive/10 p-2 rounded">
                {data.error}
              </div>
            )}
          </div>
        );
      case 'answer':
        return (
          <div className="font-mono text-sm bg-white/50 p-3 rounded max-h-96 overflow-auto">
            {data.answer || '无答案'}
          </div>
        );
      case 'error':
        return (
          <div className="text-sm text-destructive">
            {data.message || JSON.stringify(data, null, 2)}
          </div>
        );
      default:
        return (
          <pre className="text-xs whitespace-pre-wrap overflow-x-auto">
            {JSON.stringify(data, null, 2)}
          </pre>
        );
    }
  };

  return (
    <div className="h-full flex flex-col bg-gradient-to-b from-background to-muted/30">
      <div className="p-3 border-b flex items-center justify-between bg-card/50 backdrop-blur-sm">
        <div>
          <h2 className="text-sm font-semibold gradient-text">执行日志</h2>
          <p className="text-xs text-muted-foreground mt-0.5">实时追踪 ReAct 循环执行过程</p>
        </div>
        <Badge variant="secondary" className="shadow-sm text-xs">{logs.length} 条记录</Badge>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-3 space-y-1.5">
          {logs.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-muted/50 mb-4">
                <Info className="h-8 w-8" />
              </div>
              <p className="font-medium text-sm">暂无日志记录</p>
              <p className="text-xs mt-2 opacity-70">输入任务并点击"运行任务"开始</p>
            </div>
          ) : (
            logs.map((entry, index) => (
              <div
                key={index}
                className={cn(
                  'p-2.5 rounded-lg border-l-4 shadow-sm animate-in',
                  getLogStyle(entry.type)
                )}
                style={{ animationDelay: `${index * 30}ms` }}
              >
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-1.5">
                    <div className="p-1 rounded-md bg-background/50">
                      {getIcon(entry.type)}
                    </div>
                    <span className="text-xs font-bold uppercase tracking-wider">
                      {entry.type}
                    </span>
                    {entry.iteration && (
                      <Badge variant="outline" className="text-xs font-medium">
                        迭代 {entry.iteration}
                      </Badge>
                    )}
                  </div>
                  <span className="text-xs font-mono opacity-60">
                    {formatTimestamp(entry.timestamp)}
                  </span>
                </div>
                <div className="pl-7">
                  {formatContent(entry)}
                </div>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
