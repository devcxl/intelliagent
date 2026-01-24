import { useState, useEffect } from 'react';
import { Bot, AlertCircle } from 'lucide-react';
import { Sidebar } from '@/components/Sidebar';
import { LogViewer } from '@/components/LogViewer';
import { InputArea } from '@/components/InputArea';
import { useWebSocket } from '@/hooks/useWebSocket';
import type { Session } from '@/types';

export default function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const { isConnected, messages, error, connect, sendMessage, clearMessages } = useWebSocket();

  useEffect(() => {
    connect();
  }, [connect]);

  const createSession = () => {
    const newSession: Session = {
      id: Date.now().toString(),
      title: `会话 ${sessions.length + 1}`,
      task: '',
      logs: [],
      status: 'idle',
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    setSessions([...sessions, newSession]);
    setCurrentSessionId(newSession.id);
  };

  const selectSession = (id: string) => {
    setCurrentSessionId(id);
    clearMessages();
  };

  const deleteSession = (id: string) => {
    setSessions(sessions.filter(s => s.id !== id));
    if (currentSessionId === id) {
      setCurrentSessionId(sessions.length > 1 ? sessions[0].id : null);
      clearMessages();
    }
  };

  const handleRun = (task: string, maxIterations: number) => {
    if (!currentSessionId) {
      createSession();
    }

    sendMessage({
      task,
      max_iterations: maxIterations,
    });

    setIsRunning(true);

    setSessions(prev => prev.map(session => {
      if (session.id === (currentSessionId || sessions[sessions.length - 1]?.id)) {
        return {
          ...session,
          title: task.slice(0, 30) + (task.length > 30 ? '...' : ''),
          task,
          status: 'running',
          updatedAt: new Date(),
        };
      }
      return session;
    }));
  };

  const handleStop = () => {
    setIsRunning(false);
    
    if (currentSessionId) {
      setSessions(prev => prev.map(session => {
        if (session.id === currentSessionId) {
          return {
            ...session,
            status: 'error',
            updatedAt: new Date(),
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

          return {
            ...session,
            logs: updatedLogs,
            status,
            updatedAt: new Date(),
          };
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

  return (
    <div className="h-screen flex flex-col bg-background">
      <header className="border-b bg-gradient-to-r from-card via-card/95 to-card px-6 py-3 flex items-center gap-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-1.5 rounded-lg bg-primary/10">
            <Bot className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold gradient-text">IntelliAgent</h1>
            <span className="text-xs text-muted-foreground block">
              基于 ReAct 循环的代码开发助手
            </span>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted/50">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
            <span className="text-sm text-muted-foreground font-medium">
              {isConnected ? '已连接' : '未连接'}
            </span>
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <div className="w-80 flex-shrink-0">
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
        <div className="fixed bottom-4 right-4 bg-destructive text-destructive-foreground px-4 py-3 rounded-xl shadow-lg animate-in flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}
    </div>
  );
}
