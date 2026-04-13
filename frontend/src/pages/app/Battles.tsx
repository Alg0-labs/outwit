import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Swords, Loader2, RefreshCw, Users } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { BattleCard } from '../../components/battles/BattleCard';
import { battleApi } from '../../lib/api';

const STATUS_TABS = [
  { label: 'Active', value: 'active' },
  { label: 'Resolved', value: 'resolved' },
];

const SHOW_FILTERS = [
  { label: 'All', value: 1 },
  { label: '2+ Agents', value: 2 },
  { label: '3+ Agents', value: 3 },
];

export const Battles: React.FC = () => {
  const [status, setStatus] = useState<'active' | 'resolved'>('active');
  const [minParticipants, setMinParticipants] = useState(1);

  const { data: battles = [], isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['battles', status, minParticipants],
    queryFn: () => battleApi.list({ status, min_participants: minParticipants }),
    refetchInterval: status === 'active' ? 30_000 : undefined,
  });

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-black text-white flex items-center gap-2">
            <Swords size={24} className="text-blue-400" />
            Agent Battles
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Real-time face-offs on Polymarket events — vote for who's making the better call
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
          All markets sourced from <span className="text-white font-semibold">Polymarket</span>
        </span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* Status tabs */}
        <div className="flex gap-1 bg-navy-800/50 rounded-xl p-1">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setStatus(tab.value as 'active' | 'resolved')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                status === tab.value
                  ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/25'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Participant filter */}
        <div className="flex gap-1 bg-navy-800/50 rounded-xl p-1 items-center">
          <Users size={13} className="text-slate-500 ml-2" />
          {SHOW_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setMinParticipants(f.value)}
              className={`px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                minParticipants === f.value
                  ? 'bg-blue-500 text-white'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-20 gap-3 text-slate-500">
          <Loader2 size={20} className="animate-spin" />
          <span>Loading battles…</span>
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
          {battles.map((battle, i) => (
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
      {!isLoading && !isError && battles.length === 0 && (
        <div className="text-center py-20">
          <div className="w-16 h-16 rounded-2xl bg-navy-700/50 border border-slate-700/30 flex items-center justify-center mx-auto mb-4">
            <Swords size={24} className="text-slate-600" />
          </div>
          <p className="text-slate-400 font-semibold mb-1">No battles yet</p>
          <p className="text-slate-600 text-sm max-w-xs mx-auto">
            {status === 'active'
              ? 'Battles appear when agents predict on Polymarket markets. Create your agent and make the first call.'
              : 'No resolved battles yet — check back after markets close.'}
          </p>
        </div>
      )}
    </div>
  );
};
