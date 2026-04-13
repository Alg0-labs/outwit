import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Clock, Users, ArrowRight, Swords, ExternalLink } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { AgentAvatar } from '../ui/AgentAvatar';
import type { BattleApiResponse, BattleParticipant } from '../../lib/api';

interface BattleCardProps {
  battle: BattleApiResponse;
  compact?: boolean;
}

const CATEGORY_META: Record<string, { emoji: string; label: string }> = {
  ipl: { emoji: '🏏', label: 'IPL 2026' },
  geopolitics: { emoji: '⚔️', label: 'Geopolitics' },
};

const confidenceColor = (conf: number) => {
  if (conf >= 70) return 'bg-emerald-500';
  if (conf >= 55) return 'bg-blue-500';
  return 'bg-amber-500';
};

const predictionStyle = (pred: string) =>
  pred === 'YES'
    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
    : 'bg-red-500/15 text-red-400 border-red-500/20';

// ── Single participant card ───────────────────────────────────────────────────
const ParticipantCard: React.FC<{ p: BattleParticipant; rank: number; totalVotes: number }> = ({
  p,
  rank,
  totalVotes,
}) => (
  <div className="flex-1 min-w-[140px] rounded-xl bg-navy-700/40 border border-slate-700/30 p-3 flex flex-col gap-2">
    <div className="flex items-center gap-2">
      <AgentAvatar avatar={p.agent_avatar} color={p.agent_color} size="sm" />
      <div className="min-w-0">
        <p className="text-xs font-semibold text-white truncate">{p.agent_name}</p>
        <p className="text-[10px] text-slate-500 truncate">@{p.agent_owner_username}</p>
      </div>
    </div>

    <div className="flex items-center gap-1.5">
      <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${predictionStyle(p.prediction)}`}>
        {p.prediction}
      </span>
      <span className="text-xs font-bold text-white ml-auto">{p.confidence}%</span>
    </div>

    <div className="h-1 bg-navy-600 rounded-full overflow-hidden">
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${p.confidence}%` }}
        transition={{ duration: 0.7, delay: rank * 0.1 }}
        className={`h-full rounded-full ${confidenceColor(p.confidence)}`}
      />
    </div>

    <div className="flex items-center gap-1 text-slate-500 text-[10px]">
      <Users size={9} />
      <span>{p.crowd_votes} vote{p.crowd_votes !== 1 ? 's' : ''}</span>
      {totalVotes > 0 && (
        <span className="ml-auto text-blue-400 font-semibold">{p.crowd_vote_pct}%</span>
      )}
    </div>
  </div>
);

// ── Battle Card ───────────────────────────────────────────────────────────────
export const BattleCard: React.FC<BattleCardProps> = ({ battle, compact }) => {
  const navigate = useNavigate();
  const meta = CATEGORY_META[battle.market_category] ?? { emoji: '🌐', label: battle.market_category };
  const isLive = battle.status === 'active';
  const hasWinner = battle.winner_agent_ids.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      className="rounded-2xl border border-blue-500/10 bg-navy-800/60 backdrop-blur-sm overflow-hidden group transition-all duration-300 hover:border-blue-500/30 hover:shadow-[0_0_30px_rgba(59,130,246,0.08)]"
    >
      {/* Header row */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3 gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-base">{meta.emoji}</span>
          <span className="text-xs text-slate-400 font-medium">{meta.label}</span>
          {isLive && <Badge variant="live" pulse>LIVE</Badge>}
          {!isLive && hasWinner && <Badge variant="gray">Resolved</Badge>}
        </div>
        <div className="flex items-center gap-1 text-slate-500 text-xs flex-shrink-0">
          <Clock size={12} />
          <span>{battle.time_remaining}</span>
        </div>
      </div>

      {/* Question */}
      <p className="px-5 font-semibold text-white text-sm md:text-base leading-snug mb-3">
        {battle.market_question}
      </p>

      {/* Polymarket attribution */}
      <div className="px-5 mb-4 flex items-center gap-2">
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-[11px] text-slate-500">
          Live data from{' '}
          <span className="text-slate-400 font-medium">Polymarket</span>
        </span>
        <ExternalLink size={10} className="text-slate-600" />
      </div>

      {/* Participants */}
      {battle.participants.length > 0 ? (
        <div className="px-5 mb-4">
          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
            {battle.participants.map((p, i) => (
              <ParticipantCard
                key={p.agent_id}
                p={p}
                rank={i}
                totalVotes={battle.total_votes}
              />
            ))}
          </div>
        </div>
      ) : (
        <div className="px-5 mb-4 py-6 text-center text-slate-600 text-xs">
          No agents have predicted on this market yet.
        </div>
      )}

      {/* Stats row */}
      {!compact && battle.participants.length > 0 && (
        <div className="px-5 mb-4 flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-1.5">
            <Swords size={12} className="text-blue-400" />
            <span>
              <span className="text-white font-semibold">{battle.participants.length}</span>{' '}
              agent{battle.participants.length !== 1 ? 's' : ''} competing
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Users size={11} />
            <span>{battle.total_votes} crowd vote{battle.total_votes !== 1 ? 's' : ''}</span>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="px-5 pb-5">
        <Button
          variant="secondary"
          size="sm"
          className="w-full"
          iconRight={<ArrowRight size={14} />}
          onClick={() => navigate(`/app/battles/${battle.id}`)}
        >
          {battle.participants.length >= 2 ? 'Watch Battle' : 'View Market'}
        </Button>
      </div>
    </motion.div>
  );
};
