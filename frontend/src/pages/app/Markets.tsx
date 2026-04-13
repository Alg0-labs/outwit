import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { BarChart2, Clock, TrendingUp, Loader2, RefreshCw } from 'lucide-react';
import { MarketCard } from '../../components/markets/MarketCard';
import { marketApi, type MarketResponse } from '../../lib/api';

const CATEGORY_FILTERS = ['All', '🏏 IPL', '⚔️ Geopolitics'];
const SORT_FILTERS = ['All', 'High Volume', 'Closing Soon'];

function formatVolume(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

function toCardMarket(m: MarketResponse) {
  const closeDate = new Date(m.closes_at);
  const hoursLeft = (closeDate.getTime() - Date.now()) / 3_600_000;
  return {
    id: m.external_id,
    source: m.source ?? 'polymarket',
    question: m.question,
    yesPrice: m.yes_price,
    noPrice: m.no_price,
    volume: formatVolume(m.volume_24h),
    volumeNum: m.volume_24h,
    timeRemaining: m.time_remaining,
    category: m.category === 'ipl' ? 'IPL 2026' : 'Geopolitics',
    categoryEmoji: m.category === 'ipl' ? '🏏' : '⚔️',
    closingSoon: hoursLeft < 24,
  };
}

export const Markets: React.FC = () => {
  const [sort, setSort] = useState('All');
  const [category, setCategory] = useState('All');

  const { data: markets = [], isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['markets'],
    queryFn: () => marketApi.list(),
    refetchInterval: 60_000,
  });

  const cards = markets.map(toCardMarket).filter((m) => {
    if (sort === 'High Volume' && m.volumeNum < 50_000) return false;
    if (sort === 'Closing Soon' && !m.closingSoon) return false;
    if (category === '🏏 IPL' && m.category !== 'IPL 2026') return false;
    if (category === '⚔️ Geopolitics' && m.category !== 'Geopolitics') return false;
    return true;
  });

  const totalVolume = markets.reduce((s, m) => s + m.volume_24h, 0);
  const closingToday = markets.filter((m) => {
    const h = (new Date(m.closes_at).getTime() - Date.now()) / 3_600_000;
    return h < 24;
  }).length;

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-black text-white flex items-center gap-2">
            <BarChart2 size={24} className="text-blue-400" />
            Live Markets
          </h1>
          <p className="text-slate-400 text-sm mt-1">Real-time prediction markets — let your agent analyze any event</p>
        </div>
        <button onClick={() => refetch()}
          className="w-9 h-9 rounded-xl bg-navy-700/50 border border-slate-700/30 flex items-center justify-center text-slate-400 hover:text-blue-400 transition-colors">
          <RefreshCw size={15} className={isFetching ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="flex items-center gap-2 mb-5 px-3 py-2 rounded-xl bg-blue-500/5 border border-blue-500/10 w-fit">
        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-xs text-slate-400">
          Live data from <span className="text-white font-semibold">Polymarket</span>
        </span>
        <span className="text-slate-600">·</span>
        <span className="text-xs text-slate-500">updates every 5 min</span>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { icon: BarChart2, label: 'Open Markets', value: String(markets.length), color: 'text-blue-400' },
          { icon: Clock, label: 'Closing Today', value: String(closingToday), color: 'text-amber-400' },
          { icon: TrendingUp, label: '24h Volume', value: formatVolume(totalVolume), color: 'text-emerald-400' },
        ].map(({ icon: Icon, label, value, color }) => (
          <div key={label} className="rounded-2xl bg-navy-800/60 border border-blue-500/10 p-4 flex items-center gap-3">
            <Icon size={18} className={color} />
            <div>
              <p className={`text-lg font-bold ${color}`}>{value}</p>
              <p className="text-xs text-slate-500">{label}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-3 mb-6">
        <div className="flex gap-1 bg-navy-800/50 rounded-xl p-1">
          {SORT_FILTERS.map((f) => (
            <button key={f} onClick={() => setSort(f)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${sort === f ? 'bg-blue-500 text-white' : 'text-slate-400 hover:text-white'}`}>
              {f}
            </button>
          ))}
        </div>
        <div className="flex gap-1 bg-navy-800/50 rounded-xl p-1">
          {CATEGORY_FILTERS.map((c) => (
            <button key={c} onClick={() => setCategory(c)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${category === c ? 'bg-blue-500 text-white' : 'text-slate-400 hover:text-white'}`}>
              {c}
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20 gap-3 text-slate-500">
          <Loader2 size={20} className="animate-spin" />
          <span>Fetching live markets from Polymarket…</span>
        </div>
      )}

      {isError && (
        <div className="text-center py-16 text-slate-500">
          <p className="mb-2">Failed to load markets</p>
          <button onClick={() => refetch()} className="text-blue-400 text-sm hover:underline">Try again</button>
        </div>
      )}

      {!isLoading && !isError && (
        <div className="grid md:grid-cols-2 gap-5">
          {cards.map((market, i) => (
            <motion.div key={market.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
              <MarketCard market={market} />
            </motion.div>
          ))}
        </div>
      )}

      {!isLoading && !isError && cards.length === 0 && (
        <div className="text-center py-16 text-slate-500">No markets match your filters.</div>
      )}
    </div>
  );
};
