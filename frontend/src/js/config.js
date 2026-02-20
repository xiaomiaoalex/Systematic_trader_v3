/**
 * 前端配置
 * 支持多环境配置
 */
const AppConfig = {
    // API基础URL
    apiBaseUrl: (() => {
        const host = window.location.hostname;
        const port = window.location.port;
        
        // 开发环境
        if (host === 'localhost' || host === '127.0.0.1') {
            return `http://${host}:${port || 8080}/api`;
        }
        
        // 生产环境
        return '/api';
    })(),
    
    // WebSocket URL
    wsUrl: (() => {
        const host = window.location.hostname;
        const port = window.location.port;
        
        if (host === 'localhost' || host === '127.0.0.1') {
            return `ws://${host}:${port || 8080}/ws`;
        }
        
        return `wss://${window.location.host}/ws`;
    })(),
    
    // 刷新间隔（毫秒）
    refreshInterval: 30000,
    
    // 图表颜色
    chartColors: {
        primary: '#f0b90b',
        success: '#0ecb81',
        danger: '#f6465d',
        text: '#848e9c',
        grid: '#2b3139'
    }
};
