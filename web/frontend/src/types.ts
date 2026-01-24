export type LogEntryType = 'thought' | 'action' | 'observation' | 'answer' | 'error' | 'info';

export interface LogEntry {
  type: LogEntryType;
  iteration?: number;
  data: {
    reasoning?: string;
    is_complete?: boolean;
    tool?: string;
    args?: Record<string, any>;
    status?: 'success' | 'error';
    execution_time?: number;
    error?: string;
    answer?: string;
    message?: string;
    [key: string]: any;
  };
  timestamp?: string;
}

export interface Session {
  id: string;
  title: string;
  task: string;
  logs: LogEntry[];
  status: 'idle' | 'running' | 'completed' | 'error';
  createdAt: Date;
  updatedAt: Date;
}

export interface WebSocketMessage {
  type: 'start' | 'step' | 'complete' | 'error';
  data: any;
}
