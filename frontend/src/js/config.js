/**
 * 前端配置
 * 支持多环境配置
 */
const AppConfig = {
    // API基础URL
    apiBaseUrl: (() => {
        const host = window.location.hostname;
        
        // 开发环境：无论前端在哪个端口启动，API 请求强制打向后端的 8080 端口
        if (host === 'localhost' || host === '127.0.0.1') {
            return `http://${host}:8080/api`;
        }
        
        // 生产环境 (使用 Nginx 反向代理时的相对路径)
        return '/api';
    })(),
    
    // WebSocket URL (目前没用到，但保持一致)
    wsUrl: (() => {
        const host = window.location.hostname;
        
        // 强制指向后端的 8080 端口
        if (host === 'localhost' || host === '127.0.0.1') {
            return `ws://${host}:8080/ws`;
        }
        
        return `wss://${window.location.host}/ws`;
    })(),
    
    // 刷新间隔（毫秒）
    refreshInterval: 30000,
    
    // 图表颜色 (确保在这里被包含在 AppConfig 内部)
    chartColors: {
        primary: '#f0b90b',
        success: '#0ecb81',
        danger: '#f6465d',
        text: '#848e9c',
        grid: '#2b3139'
    }
}; // 这里才是真正的结尾