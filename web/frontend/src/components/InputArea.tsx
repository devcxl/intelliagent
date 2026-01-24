import { useState } from 'react';
import { Send, Square, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card } from '@/components/ui/card';

interface InputAreaProps {
  isRunning: boolean;
  onRun: (task: string, maxIterations: number) => void;
  onStop: () => void;
  onClear: () => void;
  disabled?: boolean;
}

export function InputArea({ isRunning, onRun, onStop, onClear, disabled }: InputAreaProps) {
  const [task, setTask] = useState('');
  const [maxIterations, setMaxIterations] = useState(10);

  const handleRun = () => {
    const trimmedTask = task.trim();
    if (trimmedTask) {
      onRun(trimmedTask, maxIterations);
      setTask('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleRun();
    }
  };

  return (
    <div className="border-t bg-gradient-to-t from-muted/20 to-card p-4">
      <div className="flex items-center gap-4 mb-3">
        <div className="flex items-center gap-2">
          <label htmlFor="max-iterations" className="text-sm font-medium text-foreground">
            最大迭代次数：
          </label>
          <select
            id="max-iterations"
            value={maxIterations}
            onChange={(e) => setMaxIterations(Number(e.target.value))}
            disabled={isRunning || disabled}
            className="px-3 py-1.5 text-sm border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-ring/50 disabled:opacity-50 transition-shadow"
          >
            <option value={5}>5 次</option>
            <option value={10}>10 次（推荐）</option>
            <option value={15}>15 次</option>
            <option value={20}>20 次</option>
          </select>
        </div>

        <div className="ml-auto flex gap-2">
          {!isRunning && (
            <Button variant="outline" size="sm" onClick={onClear} disabled={disabled} className="hover:bg-destructive/10 hover:text-destructive">
              <Trash2 className="h-4 w-4 mr-1" />
              清空日志
            </Button>
          )}
        </div>
      </div>

      <Card className="p-4 shadow-sm hover:shadow-md transition-shadow">
        <Textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入你的任务，例如：创建一个 Python 文件并编写测试..."
          disabled={isRunning || disabled}
          className="min-h-[100px] resize-none border-0 focus-visible:ring-0 p-0 text-base leading-relaxed"
        />
        
        <div className="flex items-center justify-between mt-4">
          <p className="text-xs text-muted-foreground flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground text-xs font-mono">Ctrl</kbd>
            <span>+</span>
            <kbd className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground text-xs font-mono">Enter</kbd>
            <span className="ml-1">快速提交</span>
          </p>
          
          <div className="flex gap-2">
            {isRunning ? (
              <Button variant="destructive" onClick={onStop} className="shadow-sm hover:shadow-md transition-all">
                <Square className="h-4 w-4 mr-1.5" />
                停止任务
              </Button>
            ) : (
              <Button onClick={handleRun} disabled={!task.trim() || disabled} className="shadow-sm hover:shadow-md transition-all">
                <Send className="h-4 w-4 mr-1.5" />
                运行任务
              </Button>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
