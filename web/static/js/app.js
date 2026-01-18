
let ws = null;
let isRunning = false;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;


const taskInput = document.getElementById('task-input');
const runBtn = document.getElementById('run-btn');
const stopBtn = document.getElementById('stop-btn');
const clearBtn = document.getElementById('clear-btn');
const outputLog = document.getElementById('output-log');
const statusBadge = document.getElementById('status-badge');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const maxIterationsSelect = document.getElementById('max-iterations');


/**
 * 更新状态徽章
 */
function updateStatus(status) {
    statusBadge.className = 'status-badge ' + status;
    
    switch (status) {
        case 'waiting':
            statusText.textContent = '等待任务...';
            break;
        case 'running':
            statusText.textContent = '运行中...';
            break;
        case 'completed':
            statusText.textContent = '任务完成';
            break;
        case 'error':
            statusText.textContent = '发生错误';
            break;
        default:
            statusText.textContent = '未知状态';
    }
}

/**
 * 设置运行状态
 */
function setRunningState(running) {
    isRunning = running;
    runBtn.disabled = running;
    stopBtn.disabled = !running;
    
    if (running) {
        runBtn.innerHTML = '<span class="btn-icon">⏳</span> 运行中...';
        taskInput.disabled = true;
    } else {
        runBtn.innerHTML = '<span class="btn-icon">🚀</span> 运行任务';
        taskInput.disabled = false;
    }
}

/**
 * 清空日志
 */
function clearLog() {
    outputLog.innerHTML = '';
}

/**
 * 添加日志条目
 */
function appendLogEntry(entry) {
    const div = document.createElement('div');
    div.className = `log-entry ${entry.type}`;
    div.innerHTML = formatEntry(entry);
    outputLog.appendChild(div);
    
    // 自动滚动到底部
    outputLog.scrollTop = outputLog.scrollHeight;
}

/**
 * 格式化日志条目
 */
function formatEntry(entry) {
    const timestamp = new Date().toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    
    let content = '';
    
    switch (entry.type) {
        case 'thought':
            content = `
                <div class="log-entry-header">
                    <span class="log-type">💭 Thought</span>
                    <span class="log-iteration">迭代 ${entry.iteration}</span>
                    <span class="log-timestamp">${timestamp}</span>
                </div>
                <div class="log-content">
                    ${escapeHtml(entry.data.reasoning)}
                </div>
            `;
            break;
            
        case 'action':
            content = `
                <div class="log-entry-header">
                    <span class="log-type">🔧 Action</span>
                    <span class="log-iteration">迭代 ${entry.iteration}</span>
                    <span class="log-timestamp">${timestamp}</span>
                </div>
                <div class="log-content">
                    <span class="tool-name">${escapeHtml(entry.data.tool)}</span>
                    ${entry.data.args && Object.keys(entry.data.args).length > 0 
                        ? `<div class="tool-args">${escapeHtml(JSON.stringify(entry.data.args, null, 2))}</div>`
                        : ''}
                </div>
            `;
            break;
            
        case 'observation':
            const observation = entry.data;
            const isSuccess = observation.status === 'success';
            const icon = isSuccess ? '✅' : '❌';
            
            content = `
                <div class="log-entry-header">
                    <span class="log-type">👁 Observation</span>
                    <span class="log-iteration">迭代 ${entry.iteration}</span>
                    <span class="log-timestamp">${timestamp}</span>
                </div>
                <div class="log-content">
                    <span style="margin-right: 8px;">${icon}</span>
                    <span>${isSuccess ? '执行成功' : '执行失败'}</span>
                    ${observation.execution_time 
                        ? `<span style="margin-left: 8px; color: #6c757d;">耗时: ${observation.execution_time.toFixed(2)}s</span>`
                        : ''}
                    ${observation.error 
                        ? `<div style="margin-top: 8px; color: #dc3545;">${escapeHtml(observation.error)}</div>`
                        : ''}
                </div>
            `;
            break;
            
        case 'answer':
            content = `
                <div class="log-entry-header">
                    <span class="log-type">🎉 Answer</span>
                    <span class="log-iteration">迭代 ${entry.iteration}</span>
                    <span class="log-timestamp">${timestamp}</span>
                </div>
                <div class="log-content">
                    <span class="tool-name">最终答案</span>
                    ${entry.data.answer 
                        ? `<div class="code-block">${escapeHtml(entry.data.answer)}</div>`
                        : '<span style="color: #6c757d;">无答案</span>'}
                </div>
            `;
            break;
            
        case 'error':
            content = `
                <div class="log-entry-header">
                    <span class="log-type">⚠️ Error</span>
                    <span class="log-timestamp">${timestamp}</span>
                </div>
                <div class="log-content">
                    ${escapeHtml(entry.message)}
                </div>
            `;
            break;
            
        default:
            content = `
                <div class="log-entry-header">
                    <span class="log-type">📄 Info</span>
                    <span class="log-timestamp">${timestamp}</span>
                </div>
                <div class="log-content">
                    ${escapeHtml(JSON.stringify(entry.data, null, 2))}
                </div>
            `;
    }
    
    return content;
}

/**
 * HTML 转义（防止 XSS）
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 显示错误提示
 */
function showError(message) {
    const entry = {
        type: 'error',
        data: { message }
    };
    appendLogEntry(entry);
    updateStatus('error');
    setRunningState(false);
}


/**
 * 连接 WebSocket
 */
function connectWebSocket() {
    if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
        console.log('WebSocket 已连接或正在连接');
        return;
    }
    
    updateStatus('waiting');
    
    // 构建 WebSocket URL（自动检测协议）
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname || 'localhost';
    const port = window.location.port || '8000';
    const wsUrl = `${protocol}//${host}:${port}/ws/run`;
    
    console.log(`连接 WebSocket: ${wsUrl}`);
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = handleWebSocketOpen;
    ws.onmessage = handleWebSocketMessage;
    ws.onerror = handleWebSocketError;
    ws.onclose = handleWebSocketClose;
}

/**
 * WebSocket 连接打开
 */
function handleWebSocketOpen() {
    console.log('WebSocket 连接已建立');
    updateStatus('waiting');
    reconnectAttempts = 0;
}

/**
 * WebSocket 消息处理
 */
function handleWebSocketMessage(event) {
    try {
        const data = JSON.parse(event.data);
        console.log('收到消息:', data);
        
        switch (data.type) {
            case 'start':
                updateStatus('running');
                setRunningState(true);
                appendLogEntry({
                    type: 'info',
                    data: { message: `任务已开始（最大迭代: ${data.data.max_iterations} 次）` }
                });
                break;
                
            case 'step':
                if (data.data) {
                    appendLogEntry({
                        type: data.data.type,
                        iteration: data.data.iteration,
                        data: data.data.data
                    });
                }
                break;
                
            case 'complete':
                updateStatus('completed');
                setRunningState(false);
                appendLogEntry({
                    type: 'answer',
                    iteration: data.data.iteration || '-',
                    data: { answer: data.data.message || '任务执行完成' }
                });
                break;
                
            case 'error':
                showError(data.data.error || '未知错误');
                break;
                
            default:
                console.warn('未知消息类型:', data.type);
        }
    } catch (e) {
        console.error('解析 WebSocket 消息失败:', e);
    }
}

/**
 * WebSocket 错误处理
 */
function handleWebSocketError(error) {
    console.error('WebSocket 错误:', error);
    updateStatus('error');
    
    appendLogEntry({
        type: 'error',
        data: { message: `WebSocket 连接错误: ${error.message || '未知错误'}` }
    });
    
    setRunningState(false);
}

/**
 * WebSocket 关闭处理
 */
function handleWebSocketClose(event) {
    console.log('WebSocket 连接已关闭', event);
    
    if (isRunning && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        // 尝试重连
        reconnectAttempts++;
        console.log(`尝试重连 (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
        setTimeout(connectWebSocket, 2000 * reconnectAttempts);
    } else {
        // 重连失败或正常关闭
        updateStatus('waiting');
        setRunningState(false);
    }
}

/**
 * 提交任务
 */
function runTask() {
    const task = taskInput.value.trim();
    
    if (!task) {
        showError('请输入任务描述');
        return;
    }
    
    const maxIterations = parseInt(maxIterationsSelect.value);
    
    // 清空之前的日志
    clearLog();
    
    // 发送任务请求
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            task: task,
            max_iterations: maxIterations
        }));
    } else {
        showError('WebSocket 未连接，正在尝试重连...');
        connectWebSocket();
        
        // 等待连接后发送
        setTimeout(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    task: task,
                    max_iterations: maxIterations
                }));
            }
        }, 1000);
    }
}

/**
 * 停止任务
 */
function stopTask() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close(1000, '用户手动停止');
    }
    
    setRunningState(false);
    updateStatus('waiting');
    
    appendLogEntry({
        type: 'error',
        data: { message: '任务已手动停止' }
    });
}


runBtn.addEventListener('click', runTask);
stopBtn.addEventListener('click', stopTask);
clearBtn.addEventListener('click', () => {
    clearLog();
    updateStatus('waiting');
});

// 支持快捷键（Ctrl+Enter 提交任务）
taskInput.addEventListener('keydown', (event) => {
    if (event.ctrlKey && event.key === 'Enter') {
        event.preventDefault();
        runTask();
    }
});


console.log('IntelliAgent 前端已加载');
console.log('尝试连接 WebSocket...');

// 页面加载完成后连接 WebSocket
window.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
});

// 页面关闭时清理
window.addEventListener('beforeunload', () => {
    if (ws) {
        ws.close();
    }
});
