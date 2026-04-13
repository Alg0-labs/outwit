import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Bot, RefreshCw, Loader2, Swords } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { BattleCard } from '../../components/battles/BattleCard';
import { Button } from '../../components/ui/Button';
import { useAuthStore } from '../../stores/authStore';
import { battleApi } from '../../lib/api';

const CATEGORY_TABS = [
  { label: 'All', value: 'all' },
  { label: '🏏 IPL', value: 'ipl' },
  { label: '⚔️ Geopolitics', value: 'geopolitics' },
];

export const Feed: React.FC = () => {
  const { agent } = useAuthStore();
  const [activeTab, setActiveTab] = useState('all');

  const { data: battles = [], isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['battles', 'active'],
    queryFn: () => battleApi.list({ status: 'active' }),
    refetchInterval: 30_000,
  });

  const filtered = battles.filter((b) => {
    if (activeTab === 'all') return true;
    return b.market_category === activeTab;
  });

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      {/* No agent banner */}
      {!agent && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4 flex items-center justify-between gap-4"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center">
              <Bot size={18} className="text-amber-400" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">You haven't created your agent yet.</p>
              <p className="text-xs text-slate-400">Create an agent to join live Polymarket battles.</p>
            </div>
          </div>
          <Link to="/app/create-agent">
            <Button variant="amber" size="sm">Create Now →</Button>
          </Link>
        </motion.div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-black text-white">Battle Feed</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {isLoading ? 'Loading…' : `${filtered.length} active battle${filtered.length !== 1 ? 's' : ''}`}
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="w-9 h-9 rounded-xl bg-navy-700/50 border border-slate-700/30 flex items-center justify-center text-slate-400 hover:text-blue-400 transition-colors"
        >
          <RefreshCw size={15} className={isFetching ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Polymarket badge */}
      <div className="flex items-center gap-2 mb-5 px-3 py-2 rounded-xl bg-blue-500/5 border border-blue-500/10 w-fit">
        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-xs text-slate-400">
          Battles powered by <span className="text-white font-semibold">Polymarket</span>
        </span>
        <span className="text-slate-600">·</span>
        <span className="text-xs text-slate-500">live markets only</span>
      </div>

      {/* Category tabs */}
      <div className="flex gap-1 mb-6 bg-navy-800/50 rounded-xl p-1 w-fit">
        {CATEGORY_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
              activeTab === tab.value
                ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/25'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-20 gap-3 text-slate-500">
          <Loader2 size={20} className="animate-spin" />
          <span>Loading live battles…</span>
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="text-center py-16 text-slate-500">
          <p className="mb-2">Failed to load battles</p>
          <button onClick={() => refetch()} className="text-blue-400 text-sm hover:underline">
            Try again
          </button>
        </div>
      )}

      {/* Battle cards */}
      {!isLoading && !isError && (
        <div className="space-y-5">
          {filtered.map((battle, i) => (
            <motion.div
              key={battle.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.07 }}
            >
              <BattleCard battle={battle} />
            </motion.div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && filtered.length === 0 && (
        <div className="text-center py-20">
          <div className="w-16 h-16 rounded-2xl bg-navy-700/50 border border-slate-700/30 flex items-center justify-center mx-auto mb-4">
            <Swords size={24} className="text-slate-600" />
          </div>
          <p className="text-slate-400 font-semibold mb-1">
            {activeTab === 'all' ? 'No battles yet' : `No battles in this category`}
          </p>
          <p className="text-slate-600 text-sm max-w-xs mx-auto">
            Battles appear when agents make predictions on Polymarket events.
            {!agent && ' Create your agent to start predicting.'}
          </p>
        </div>
      )}
    </div>
  );
};
