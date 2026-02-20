/**
 * 主应用
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
        
        // 方法
        const formatBalance = (value) => {
            return parseFloat(value || 0).toFixed(2);
        };
        
        const refreshData = async () => {
            try {
                const [account, strat, risk] = await Promise.all([
                    API.getAccount(),
                    API.getStrategies(),
                    API.getRiskStatus()
                ]);
                
                accountBalance.value = account.totalWalletBalance || 0;
                strategies.value = strat || [];
                dailyPnL.value = risk?.dailyPnl || 0;
                maxDrawdown.value = risk?.currentDrawdown || 0;
            } catch (e) {
                console.error('刷新数据失败:', e);
            }
        };
        
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
        
        // 生命周期
        onMounted(async () => {
            await refreshData();
            
            // 定时刷新
            refreshTimer = setInterval(refreshData, AppConfig.refreshInterval);
        });
        
        onUnmounted(() => {
            if (refreshTimer) {
                clearInterval(refreshTimer);
            }
        });
        
        return {
            currentView,
            accountBalance,
            dailyPnL,
            winRate,
            maxDrawdown,
            strategies,
            backtestConfig,
            backtestRunning,
            backtestResult,
            menuItems,
            currentViewTitle,
            formatBalance,
            refreshData,
            loadStrategies,
            toggleStrategy,
            runBacktest
        };
    }
}).mount('#app');
