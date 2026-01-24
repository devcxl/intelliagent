import { useState, useEffect } from 'react';
import { Bot, AlertCircle, Loader2 } from 'lucide-react';
import { Sidebar } from '@/components/Sidebar';
import { LogViewer } from '@/components/LogViewer';
import { InputArea } from '@/components/InputArea';
import { ThemeToggle } from '@/components/ThemeToggle';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { useWebSocket } from '@/hooks/useWebSocket';
import { sessionApi } from '@/lib/session-api';

interface AppSession {
  id: string;
  title: string;
  task: string;
  logs: any[];
  status: 'idle' | 'running' | 'completed' | 'error';
  createdAt: string;
  updatedAt: string;
}

export default function App() {
  const [sessions, setSessions] = useState<AppSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { isConnected, messages, connect, sendMessage, clearMessages } = useWebSocket();

  useEffect(() => {
    connect();
    loadSessions();
  }, [connect]);

  const loadSessions = async () => {
    try {
      setIsLoading(true);
      const fetchedSessions = await sessionApi.getSessions();
      setSessions(fetchedSessions);
      
      if (fetchedSessions.length > 0) {
        setCurrentSessionId(fetchedSessions[0].id);
      }
    } catch (err) {
      console.error('加载会话失败:', err);
      setError('加载会话失败');
    } finally {
      setIsLoading(false);
    }
  };

  const createSession = async () => {
    try {
      const newSession = await sessionApi.createSession(`会话 ${sessions.length + 1}`);
      setSessions(prev => [newSession, ...prev]);
      setCurrentSessionId(newSession.id);
      clearMessages();
    } catch (err) {
      console.error('创建会话失败:', err);
      setError('创建会话失败');
    }
  };

  const selectSession = async (id: string) => {
    try {
      setCurrentSessionId(id);
      clearMessages();
      
      const session = await sessionApi.getSession(id);
      setSessions(prev => prev.map(s => s.id === id ? session : s));
    } catch (err) {
      console.error('获取会话失败:', err);
      setError('获取会话失败');
    }
  };

  const deleteSession = async (id: string) => {
    try {
      await sessionApi.deleteSession(id);
      setSessions(prev => prev.filter(s => s.id !== id));
      
      if (currentSessionId === id) {
        const remaining = sessions.filter(s => s.id !== id);
        setCurrentSessionId(remaining.length > 0 ? remaining[0].id : null);
        clearMessages();
      }
    } catch (err) {
      console.error('删除会话失败:', err);
      setError('删除会话失败');
    }
  };

  const handleRun = async (task: string, maxIterations: number) => {
    let sessionId = currentSessionId;

    if (!sessionId) {
      const newSession = await sessionApi.createSession(task.slice(0, 30) + (task.length > 30 ? '...' : ''), task);
      setSessions(prev => [newSession, ...prev]);
      sessionId = newSession.id;
      setCurrentSessionId(sessionId);
    } else {
      await sessionApi.updateSession(sessionId, {
        title: task.slice(0, 30) + (task.length > 30 ? '...' : ''),
        task,
        status: 'running'
      });
      setSessions(prev => prev.map(s => 
        s.id === sessionId ? { ...s, title: task.slice(0, 30) + (task.length > 30 ? '...' : ''), task, status: 'running' as const, updatedAt: new Date().toISOString() } : s
      ));
    }

    sendMessage({
      task,
      max_iterations: maxIterations,
    });

    setIsRunning(true);
  };

  const handleStop = () => {
    setIsRunning(false);
    
    if (currentSessionId) {
      sessionApi.updateSession(currentSessionId, { status: 'error' }).catch(err => {
        console.error('更新会话状态失败:', err);
      });
      
      setSessions(prev => prev.map(session => {
        if (session.id === currentSessionId) {
          return {
            ...session,
            status: 'error',
            updatedAt: new Date().toISOString()
          };
        }
        return session;
      }));
    }
  };

  const handleClear = () => {
    clearMessages();
  };

  useEffect(() => {
    if (messages.length > 0 && currentSessionId) {
      const lastMessage = messages[messages.length - 1];
      
      setSessions(prev => prev.map(session => {
        if (session.id === currentSessionId) {
          const updatedLogs = [...session.logs, lastMessage];
          let status = session.status;

          if (lastMessage.type === 'answer') {
            status = 'completed';
          } else if (lastMessage.type === 'error') {
            status = 'error';
          }

          const updatedSession = { ...session, logs: updatedLogs, status, updatedAt: new Date().toISOString() };
          
          sessionApi.updateSession(currentSessionId, {
            logs: updatedLogs,
            status: status
          }).catch(err => {
            console.error('更新会话日志失败:', err);
          });
          
          return updatedSession;
        }
        return session;
      }));
    }
  }, [messages, currentSessionId]);

  useEffect(() => {
    if (messages.some(m => m.type === 'answer' || m.type === 'error')) {
      setIsRunning(false);
    }
  }, [messages]);

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-muted-foreground">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <ThemeProvider>
      <div className="h-screen flex flex-col bg-background">
        <header className="border-b bg-gradient-to-r from-card via-card/95 to-card px-4 py-2 flex items-center gap-2 shadow-sm">
          <div className="flex items-center gap-2">
            <div className="p-1 rounded-lg bg-primary/10">
              <Bot className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h1 className="text-base font-bold gradient-text">IntelliAgent</h1>
              <span className="text-xs text-muted-foreground block leading-tight">
                ReAct 代码开发助手
              </span>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-muted/50">
              <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
              <span className="text-xs text-muted-foreground font-medium">
                {isConnected ? '已连接' : '未连接'}
              </span>
            </div>
            <ThemeToggle />
          </div>
        </header>

        <div className="flex-1 flex overflow-hidden">
          <div className="w-64 flex-shrink-0">
            <Sidebar
              sessions={sessions}
              currentSessionId={currentSessionId}
              onCreateSession={createSession}
              onSelectSession={selectSession}
              onDeleteSession={deleteSession}
            />
          </div>

          <div className="flex-1 flex flex-col">
            <div className="flex-1 overflow-hidden">
              <LogViewer logs={messages} />
            </div>

            <InputArea
              isRunning={isRunning}
              onRun={handleRun}
              onStop={handleStop}
              onClear={handleClear}
              disabled={!isConnected}
            />
          </div>
        </div>

        {error && (
          <div className="fixed bottom-4 right-4 bg-destructive text-destructive-foreground px-3 py-2 rounded-lg shadow-lg animate-in flex items-center gap-2 text-sm">
            <AlertCircle className="h-3.5 w-3.5" />
            {error}
          </div>
        )}
      </div>
    </ThemeProvider>
  );
}
