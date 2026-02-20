/**
 * API封装
 */
const API = {
    baseUrl: AppConfig.apiBaseUrl,
    
    async request(method, endpoint, data = null) {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        
        if (data) {
            options.body = JSON.stringify(data);
        }
        
        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`, options);
            
            if (!response.ok) {
                throw new Error(`API Error: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API请求失败:', error);
            throw error;
        }
    },
    
    // 系统状态
    async getStatus() {
        return this.request('GET', '/status');
    },
    
    // 账户
    async getAccount() {
        return this.request('GET', '/account');
    },
    
    async getBalance() {
        return this.request('GET', '/account/balance');
    },
    
    // 持仓和交易
    async getPositions() {
        return this.request('GET', '/positions');
    },
    
    async getTrades(limit = 50) {
        return this.request('GET', `/trades?limit=${limit}`);
    },
    
    // 策略
    async getStrategies() {
        return this.request('GET', '/strategies');
    },
    
    async enableStrategy(name) {
        return this.request('POST', `/strategies/${name}/enable`);
    },
    
    async disableStrategy(name) {
        return this.request('POST', `/strategies/${name}/disable`);
    },
    
    async updateStrategyParams(name, params) {
        return this.request('PUT', `/strategies/${name}/params`, params);
    },
    
    // 回测
    async runBacktest(config) {
        return this.request('POST', '/backtest/run', config);
    },
    
    // 风险
    async getRiskStatus() {
        return this.request('GET', '/risk/status');
    },
    
    async updateRiskParams(params) {
        return this.request('PUT', '/risk/params', params);
    },
    
    // K线
    async getKlines(symbol, interval, limit) {
        return this.request('GET', `/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`);
    }
};
