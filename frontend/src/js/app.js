/**
 * 主应用 (Vue 3 Composition API)
 */
const { createApp, ref, computed, onMounted, onUnmounted } = Vue;

createApp({
    setup() {
        // ================= 状态 =================
        const currentView = ref('dashboard');
        const accountBalance = ref(0);
        const dailyPnL = ref(0);
        const winRate = ref(0);
        const maxDrawdown = ref(0);
        const strategies = ref([]);
        
        // 多品种监控自选池状态
        const activeSymbols = ref([]);
        const newSymbolInput = ref('');
        const isModifyingSymbol = ref(false);

        // 交易与持仓状态
        const positions = ref([]);
        const trades = ref([]);
        
        // ================= 回测时间初始化 =================
        const today = new Date();
        const sixMonthsAgo = new Date();
        sixMonthsAgo.setMonth(today.getMonth() - 6);
        const formatDate = (date) => date.toISOString().split('T')[0];
        
        const backtestConfig = ref({ 
            strategy: 'convergence_breakout', 
            symbol: 'BTCUSDT', 
            interval: '1h', 
            initialCapital: 10000,
            startTime: formatDate(sixMonthsAgo), // 绑定开始时间，默认半年前
            endTime: formatDate(today)           // 绑定结束时间，默认今天
        });
        const backtestRunning = ref(false);
        const backtestResult = ref(null);
        
        // 定时器
        let refreshTimer = null;
        
        const menuItems = [
            { id: 'dashboard', name: '仪表盘', icon: '📊' },
            { id: 'strategy', name: '策略管理', icon: '🎯' },
            { id: 'backtest', name: '回测分析', icon: '📈' }
        ];
        
        const currentViewTitle = computed(() => {
            const item = menuItems.find(m => m.id === currentView.value);
            return item ? item.name : '';
        });
        
        // ================= 工具方法 =================
        const formatBalance = (value) => {
            const num = parseFloat(value);
            return isNaN(num) ? '0.00' : num.toFixed(2);
        };
        
        // 策略战报计算帮手函数
        const getStrategyTrades = (strategyName) => {
            return trades.value.filter(t => t.strategy === strategyName);
        };
        const getStrategyPnL = (strategyName) => {
            const strTrades = getStrategyTrades(strategyName);
            return strTrades.reduce((sum, t) => sum + (t.status === 'CLOSED' ? parseFloat(t.pnl || 0) : 0), 0);
        };
        
        // ================= 核心数据刷新 =================
        const refreshData = async () => {
            try {
                // 并行请求所有数据
                const [account, strat, risk, posData, tradesData] = await Promise.all([
                    API.getBalance(),
                    API.getStrategies(),
                    API.getRiskStatus(),
                    API.getPositions(),   // 拉取实时持仓
                    API.getTrades(50)     // 拉取最近50笔交易流水
                ]);
                
                // 稳健解析余额
                let usdt = 0;
                if (account) {
                    if (account.total && account.total.USDT !== undefined) usdt = account.total.USDT;
                    else if (account.info && account.info.totalWalletBalance !== undefined) usdt = parseFloat(account.info.totalWalletBalance);
                }
                accountBalance.value = usdt;
                
                strategies.value = strat || [];
                dailyPnL.value = risk?.dailyPnl || 0;
                maxDrawdown.value = risk?.currentDrawdown || 0;
                
                // 赋值给响应式变量
                positions.value = posData || [];
                trades.value = tradesData || [];
                
                await loadSymbols();
            } catch (e) {
                console.error('刷新数据失败:', e);
            }
        };

        // ================= 策略管理 =================
        const loadStrategies = async () => {
            try { strategies.value = await API.getStrategies(); } 
            catch (e) { console.error('加载策略失败:', e); }
        };
        
        const toggleStrategy = async (name) => {
            try {
                const strategy = strategies.value.find(s => s.name === name);
                if (strategy.enabled) await API.disableStrategy(name);
                else await API.enableStrategy(name);
                await loadStrategies();
            } catch (e) { console.error('切换策略失败:', e); }
        };

        const saveStrategyParams = async (name, params) => {
            if (!confirm(`确定要更新策略 [${name}] 的参数吗？`)) return;
            try {
                await API.updateStrategyParams(name, params);
                alert('参数更新成功！');
                await loadStrategies();
            } catch (e) { alert(`更新失败: ${e.message}`); }
        };
        
        // ================= 回测引擎 =================
        const runBacktest = async () => {
            // 前置校验逻辑：检查时间跨度
            const start = new Date(backtestConfig.value.startTime);
            const end = new Date(backtestConfig.value.endTime);
            
            if (start > end) {
                alert('⚠️ 错误：开始日期不能晚于结束日期！');
                return;
            }
            
            const diffYears = (end - start) / (1000 * 60 * 60 * 24 * 365.25);
            if (diffYears > 5) {
                alert(`⚠️ 错误：您的回测跨度为 ${diffYears.toFixed(1)} 年。\n为防止内存溢出和请求超时，单次回测最长不允许超过 5 年！`);
                return;
            }

            backtestRunning.value = true;
            try { 
                backtestResult.value = await API.runBacktest(backtestConfig.value); 
            } catch (e) { 
                alert('回测失败: ' + e.message); 
            } finally { 
                backtestRunning.value = false; 
            }
        };

        // ================= 雷达自选池 =================
        const loadSymbols = async () => {
            try { activeSymbols.value = (await API.getSymbols()).symbols || []; } 
            catch (error) { console.error("加载监控列表失败:", error); }
        };

        const addSymbol = async () => {
            const symbol = newSymbolInput.value.trim().toUpperCase();
            if (!symbol) return;
            isModifyingSymbol.value = true;
            try {
                await API.addSymbol(symbol);
                newSymbolInput.value = ''; 
                setTimeout(loadSymbols, 500); 
            } catch (error) { alert(`挂载失败: ${error.message}`); } 
            finally { isModifyingSymbol.value = false; }
        };

        const removeSymbol = async (symbol) => {
            if (!confirm(`确定要卸载监控 ${symbol} 吗？`)) return;
            try {
                await API.removeSymbol(symbol);
                setTimeout(loadSymbols, 500);
            } catch (error) { alert(`卸载失败: ${error.message}`); }
        };
        
        // ================= 生命周期 =================
        onMounted(async () => {
            await refreshData();
            refreshTimer = setInterval(refreshData, AppConfig.refreshInterval);
        });
        
        onUnmounted(() => { if (refreshTimer) clearInterval(refreshTimer); });
        
        return {
            currentView, accountBalance, dailyPnL, winRate, maxDrawdown,
            strategies, backtestConfig, backtestRunning, backtestResult,
            activeSymbols, newSymbolInput, isModifyingSymbol,
            positions, trades,
            menuItems, currentViewTitle,
            formatBalance, refreshData, loadStrategies, toggleStrategy, 
            saveStrategyParams, runBacktest, loadSymbols, addSymbol, removeSymbol,
            getStrategyTrades, getStrategyPnL 
        };
    }
}).mount('#app');