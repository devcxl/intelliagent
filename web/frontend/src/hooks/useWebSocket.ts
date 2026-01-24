import { useEffect, useRef, useState, useCallback } from 'react';
import type { WebSocketMessage, LogEntry } from '@/types';

interface UseWebSocketReturn {
  isConnected: boolean;
  messages: LogEntry[];
  error: string | null;
  connect: () => void;
  disconnect: () => void;
  sendMessage: (message: any) => void;
  clearMessages: () => void;
}

export function useWebSocket(): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState<LogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname || 'localhost';
    const port = window.location.port || '8000';
    const wsUrl = `${protocol}//${host}:${port}/ws/run`;

    console.log(`连接 WebSocket: ${wsUrl}`);
    
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      console.log('WebSocket 连接已建立');
      setIsConnected(true);
      setError(null);
    };

    wsRef.current.onmessage = (event) => {
      try {
        const data: WebSocketMessage = JSON.parse(event.data);
        
        const logEntry: LogEntry = {
          type: data.data?.type || 'info',
          iteration: data.data?.iteration,
          data: data.data?.data || {},
          timestamp: new Date().toISOString(),
        };

        setMessages((prev) => [...prev, logEntry]);
      } catch (e) {
        console.error('解析 WebSocket 消息失败:', e);
      }
    };

    wsRef.current.onerror = (e) => {
      console.error('WebSocket 错误:', e);
      setError('WebSocket 连接错误');
      setIsConnected(false);
    };

    wsRef.current.onclose = () => {
      console.log('WebSocket 连接已关闭');
      setIsConnected(false);
    };
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
  }, []);

  const sendMessage = useCallback((message: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      setError('WebSocket 未连接');
    }
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  return {
    isConnected,
    messages,
    error,
    connect,
    disconnect,
    sendMessage,
    clearMessages,
  };
}
