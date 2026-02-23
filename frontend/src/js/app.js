/**
 * 主应用 (Vue 3 Composition API)
 */
const { createApp, ref, computed, onMounted, onUnmounted } = Vue;

createApp({
    setup() {
        // 状态
        const currentView = ref('dashboard');
        const accountBalance = ref(0);
        const dailyPnL = ref(0);
        const winRate = ref(0);
        const maxDrawdown = ref(0);
        const strategies = ref([]);
        const backtestConfig = ref({
            strategy: '',
            symbol: 'BTCUSDT',
            interval: '1h',
            initialCapital: 10000
        });
        const backtestRunning = ref(false);
        const backtestResult = ref(null);
        
        // 多品种监控自选池状态
        const activeSymbols = ref([]);
        const newSymbolInput = ref('');
        const isModifyingSymbol = ref(false);
        
        // 定时器
        let refreshTimer = null;
        
        // 菜单
        const menuItems = [
            { id: 'dashboard', name: '仪表盘', icon: '📊' },
            { id: 'strategy', name: '策略管理', icon: '🎯' },
            { id: 'backtest', name: '回测分析', icon: '📈' }
        ];
        
        // 计算属性
        const currentViewTitle = computed(() => {
            const item = menuItems.find(m => m.id === currentView.value);
            return item ? item.name : '';
        });
        
        // ================= 方法：工具类 =================
        const formatBalance = (value) => {
            const num = parseFloat(value);
            return isNaN(num) ? '0.00' : num.toFixed(2);
        };
        
        // ================= 方法：核心数据刷新 =================
        const refreshData = async () => {
            try {
                const [account, strat, risk] = await Promise.all([
                    API.getBalance(), // 获取余额
                    API.getStrategies(),
                    API.getRiskStatus()
                ]);
                
                // 🛡️ 核心修复：精准解析币安 CCXT 返回的复杂余额字典
                let usdt = 0;
                if (account) {
                    if (account.total && account.total.USDT !== undefined) {
                        usdt = account.total.USDT; // 标准 CCXT 格式
                    } else if (account.info && account.info.totalWalletBalance !== undefined) {
                        usdt = parseFloat(account.info.totalWalletBalance); // 币安原生备用格式
                    }
                }
                accountBalance.value = usdt;
                
                strategies.value = strat || [];
                dailyPnL.value = risk?.dailyPnl || 0;
                maxDrawdown.value = risk?.currentDrawdown || 0;
                
                // 加载一下雷达自选池
                await loadSymbols();
            } catch (e) {
                console.error('刷新数据失败:', e);
            }
        };
        
        // ================= 方法：策略管理 =================
        const loadStrategies = async () => {
            try {
                strategies.value = await API.getStrategies();
            } catch (e) {
                console.error('加载策略失败:', e);
            }
        };
        
        const toggleStrategy = async (name) => {
            try {
                const strategy = strategies.value.find(s => s.name === name);
                if (strategy.enabled) {
                    await API.disableStrategy(name);
                } else {
                    await API.enableStrategy(name);
                }
                await loadStrategies();
            } catch (e) {
                console.error('切换策略失败:', e);
            }
        };

        const saveStrategyParams = async (name, params) => {
            if (!confirm(`确定要更新策略 [${name}] 的参数吗？`)) return;
            try {
                await API.updateStrategyParams(name, params);
                alert('参数更新成功！');
                await loadStrategies();
            } catch (e) {
                alert(`更新失败: ${e.message}`);
            }
        };
        
        // ================= 方法：回测引擎 =================
        const runBacktest = async () => {
            backtestRunning.value = true;
            try {
                const result = await API.runBacktest(backtestConfig.value);
                backtestResult.value = result;
            } catch (e) {
                console.error('回测失败:', e);
                alert('回测失败: ' + e.message);
            } finally {
                backtestRunning.value = false;
            }
        };

        // ================= 方法：雷达自选池 =================
        const loadSymbols = async () => {
            try {
                const data = await API.getSymbols();
                activeSymbols.value = data.symbols || [];
            } catch (error) {
                console.error("加载监控列表失败:", error);
            }
        };

        const addSymbol = async () => {
            const symbol = newSymbolInput.value.trim().toUpperCase();
            if (!symbol) return;
            
            isModifyingSymbol.value = true;
            try {
                await API.addSymbol(symbol);
                newSymbolInput.value = ''; 
                setTimeout(loadSymbols, 500); 
            } catch (error) {
                alert(`挂载失败: ${error.message}`);
            } finally {
                isModifyingSymbol.value = false;
            }
        };

        const removeSymbol = async (symbol) => {
            if (!confirm(`确定要卸载监控 ${symbol} 吗？`)) return;
            try {
                await API.removeSymbol(symbol);
                setTimeout(loadSymbols, 500);
            } catch (error) {
                alert(`卸载失败: ${error.message}`);
            }
        };
        
        // ================= 生命周期 =================
        onMounted(async () => {
            // 首次加载页面时获取数据
            await refreshData();
            // 每隔指定时间（默认30秒）自动刷新
            refreshTimer = setInterval(refreshData, AppConfig.refreshInterval);
        });
        
        onUnmounted(() => {
            if (refreshTimer) clearInterval(refreshTimer);
        });
        
        // 暴露给模板使用
        return {
            currentView, accountBalance, dailyPnL, winRate, maxDrawdown,
            strategies, backtestConfig, backtestRunning, backtestResult,
            activeSymbols, newSymbolInput, isModifyingSymbol,
            menuItems, currentViewTitle,
            formatBalance, refreshData, loadStrategies, toggleStrategy, 
            saveStrategyParams, runBacktest,
            loadSymbols, addSymbol, removeSymbol
        };
    }
}).mount('#app');