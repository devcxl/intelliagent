const API_BASE_URL = '/api';

export interface Session {
  id: string;
  title: string;
  task: string;
  logs: any[];
  status: 'idle' | 'running' | 'completed' | 'error';
  createdAt: string;
  updatedAt: string;
}

export const sessionApi = {
  async getSessions(): Promise<Session[]> {
    const response = await fetch(`${API_BASE_URL}/sessions`);
    if (!response.ok) {
      throw new Error('获取会话列表失败');
    }
    const data = await response.json();
    return data.sessions;
  },

  async getSession(sessionId: string): Promise<Session> {
    const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`);
    if (!response.ok) {
      throw new Error('获取会话失败');
    }
    return response.json();
  },

  async createSession(title: string, task: string = ''): Promise<Session> {
    const response = await fetch(`${API_BASE_URL}/sessions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        title,
        task,
        status: 'idle'
      })
    });
    if (!response.ok) {
      throw new Error('创建会话失败');
    }
    return response.json();
  },

  async updateSession(
    sessionId: string,
    updates: {
      title?: string;
      task?: string;
      status?: string;
      logs?: any[];
    }
  ): Promise<Session> {
    const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(updates)
    });
    if (!response.ok) {
      throw new Error('更新会话失败');
    }
    return response.json();
  },

  async deleteSession(sessionId: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
      method: 'DELETE'
    });
    if (!response.ok) {
      throw new Error('删除会话失败');
    }
  }
};
