import React, { useEffect, useRef, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowLeft, Clock, Users, Bot, TrendingUp, Zap,
  CheckCircle2, RefreshCw, Swords, AlertCircle, Newspaper,
  Activity, MapPin, ChevronUp, ChevronDown, Minus,
} from 'lucide-react';
import { Badge } from '../../components/ui/Badge';
import { AgentAvatar } from '../../components/ui/AgentAvatar';
import { battleApi, marketApi, predictionApi, type BattleParticipant, type LiveFeedResponse, type AgentThought } from '../../lib/api';
import { useAuthStore } from '../../stores/authStore';

// ── helpers ──────────────────────────────────────────────────────────────────

const CATEGORY_META: Record<string, { emoji: string; label: string }> = {
  ipl: { emoji: '🏏', label: 'IPL 2026' },
  geopolitics: { emoji: '⚔️', label: 'Geopolitics' },
};

const predStyle = (p: string) =>
  p === 'YES'
    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
    : 'bg-red-500/15 text-red-400 border border-red-500/20';

const confColor = (c: number) =>
  c >= 70 ? 'from-emerald-600 to-emerald-400' : c >= 50 ? 'from-blue-600 to-blue-400' : 'from-amber-600 to-amber-400';

// Alternate agent side so the debate feels left-right
const sides = ['left', 'right', 'left', 'right', 'left', 'right'] as const;

// ── Typewriter (inline, lightweight) ─────────────────────────────────────────

function useTypewriter(text: string, speed = 14) {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    setIdx(0);
  }, [text]);
  useEffect(() => {
    if (idx >= text.length) return;
    const t = setTimeout(() => setIdx((i) => i + 1), speed);
    return () => clearTimeout(t);
  }, [idx, text, speed]);
  return { displayed: text.slice(0, idx), done: idx >= text.length };
}

// ── DebateEntry ───────────────────────────────────────────────────────────────

const AGENT_COLORS = [
  'border-blue-500/30 bg-blue-500/5',
  'border-purple-500/30 bg-purple-500/5',
  'border-amber-500/30 bg-amber-500/5',
  'border-emerald-500/30 bg-emerald-500/5',
  'border-rose-500/30 bg-rose-500/5',
];

const ACCENT_COLORS = ['text-blue-400', 'text-purple-400', 'text-amber-400', 'text-emerald-400', 'text-rose-400'];

interface DebateEntryProps {
  p: BattleParticipant;
  idx: number;
  isMyAgent: boolean;
  totalVotes: number;
  latestThought?: AgentThought;
}

const DebateEntry: React.FC<DebateEntryProps> = ({ p, idx, isMyAgent, totalVotes, latestThought }) => {
  const side = sides[idx % sides.length];
  const colorClass = AGENT_COLORS[idx % AGENT_COLORS.length];
  const accentClass = ACCENT_COLORS[idx % ACCENT_COLORS.length];

  // Show live reasoning if available, otherwise show original
  const reasoningText = latestThought ? latestThought.thought : p.reasoning;
  const { displayed, done } = useTypewriter(reasoningText, 10);
  const isLive = !!latestThought;
  const delta = latestThought?.confidence_delta ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0, x: side === 'left' ? -20 : 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: idx * 0.15 }}
      className={`flex gap-3 ${side === 'right' ? 'flex-row-reverse' : ''}`}
    >
      {/* Avatar column */}
      <div className="flex flex-col items-center gap-1.5 pt-1 flex-shrink-0">
        <AgentAvatar avatar={p.agent_avatar} color={p.agent_color} size="sm" showRing />
        {isMyAgent && (
          <span className="text-[9px] text-blue-400 font-bold uppercase tracking-wide">You</span>
        )}
        {/* Live pulse when agent has updated thoughts */}
        {isLive && (
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        )}
      </div>

      {/* Bubble */}
      <div className={`flex-1 max-w-[85%] rounded-2xl border p-4 ${colorClass}`}>
        {/* Agent header */}
        <div className={`flex items-center gap-2 mb-2.5 ${side === 'right' ? 'flex-row-reverse' : ''}`}>
          <p className="font-bold text-white text-sm">{p.agent_name}</p>
          <p className="text-[10px] text-slate-500">@{p.agent_owner_username}</p>
          <span className={`ml-auto text-xs font-bold px-2 py-0.5 rounded-full border ${predStyle(p.prediction)}`}>
            {p.prediction}
          </span>
        </div>

        {/* Confidence bar */}
        <div className="mb-3">
          <div className="flex justify-between text-[10px] mb-1">
            <span className="text-slate-500">Confidence</span>
            <span className={`font-bold ${accentClass} flex items-center gap-1`}>
              {p.confidence}%
              {isLive && delta !== 0 && (
                <span className={`text-[9px] flex items-center gap-0.5 ${delta > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {delta > 0 ? <ChevronUp size={9} /> : <ChevronDown size={9} />}
                  {Math.abs(delta)}
                </span>
              )}
            </span>
          </div>
          <div className="h-1.5 bg-navy-700 rounded-full overflow-hidden">
            <motion.div
              key={p.confidence}
              initial={{ width: 0 }}
              animate={{ width: `${p.confidence}%` }}
              transition={{ duration: 0.8 }}
              className={`h-full rounded-full bg-gradient-to-r ${confColor(p.confidence)}`}
            />
          </div>
        </div>

        {/* Reasoning / Live Reaction */}
        <div className={`rounded-xl p-3 ${isLive ? 'bg-emerald-900/20 border border-emerald-500/15' : 'bg-navy-800/50'}`}>
          <p className={`text-[11px] font-semibold mb-1.5 flex items-center gap-1 ${isLive ? 'text-emerald-400' : accentClass}`}>
            {isLive ? (
              <>
                <Activity size={10} />
                Live Reaction
                <span className="ml-auto text-[9px] text-slate-600 font-normal">updates on score change</span>
              </>
            ) : (
              <>
                <Bot size={10} />
                Agent Reasoning
              </>
            )}
          </p>
          {/* Headline thought */}
          <p className={`text-xs text-slate-300 leading-relaxed font-medium ${!done ? 'typewriter-cursor' : ''}`}>
            {displayed}
          </p>
          {/* Full reasoning below the headline (live thoughts only) */}
          {isLive && latestThought?.reasoning && done && (
            <div className="mt-2 pt-2 border-t border-slate-700/30">
              <p className="text-[10px] text-slate-400 leading-relaxed">{latestThought.reasoning}</p>
            </div>
          )}
        </div>

        {/* Crowd votes */}
        {totalVotes > 0 && (
          <div className="mt-2 flex items-center gap-1 text-[10px] text-slate-500">
            <Users size={9} />
            <span>{p.crowd_votes} crowd vote{p.crowd_votes !== 1 ? 's' : ''}</span>
            <span className={`ml-auto font-bold ${accentClass}`}>{p.crowd_vote_pct}%</span>
          </div>
        )}
      </div>
    </motion.div>
  );
};

// ── ThinkingBubble ────────────────────────────────────────────────────────────

const ThinkingBubble: React.FC<{ name: string; color: string; avatar: string }> = ({ name, color, avatar }) => (
  <motion.div
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -8 }}
    className="flex gap-3 items-end"
  >
    <AgentAvatar avatar={avatar} color={color} size="sm" />
    <div className="rounded-2xl bg-navy-700/60 border border-slate-700/40 px-4 py-3">
      <p className="text-[10px] text-slate-500 mb-1">{name} is re-analyzing…</p>
      <div className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{ repeat: Infinity, duration: 1.2, delay: i * 0.25 }}
            className="w-1.5 h-1.5 bg-blue-400 rounded-full block"
          />
        ))}
      </div>
    </div>
  </motion.div>
);

// ── LiveThoughtEntry ──────────────────────────────────────────────────────────

const DeltaIcon: React.FC<{ delta: number }> = ({ delta }) => {
  if (delta > 3) return <ChevronUp size={11} className="text-emerald-400" />;
  if (delta < -3) return <ChevronDown size={11} className="text-red-400" />;
  return <Minus size={11} className="text-slate-500" />;
};

const deltaColor = (delta: number) =>
  delta > 3 ? 'text-emerald-400' : delta < -3 ? 'text-red-400' : 'text-slate-500';

interface LiveThoughtProps {
  thought: AgentThought;
  participantIdx: number;
}

const LiveThoughtEntry: React.FC<LiveThoughtProps> = ({ thought, participantIdx }) => {
  const side = sides[participantIdx % sides.length];
  const colorClass = AGENT_COLORS[participantIdx % AGENT_COLORS.length];
  const accentClass = ACCENT_COLORS[participantIdx % ACCENT_COLORS.length];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.35 }}
      className={`flex gap-3 ${side === 'right' ? 'flex-row-reverse' : ''}`}
    >
      <div className="flex flex-col items-center gap-1 pt-1 flex-shrink-0">
        <AgentAvatar avatar={thought.agent_avatar} color={thought.agent_color} size="sm" />
        <div className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" />
      </div>

      <div className={`flex-1 max-w-[85%] rounded-2xl border p-3.5 ${colorClass} relative`}>
        {/* Live indicator */}
        <div className="absolute -top-2 left-3 flex items-center gap-1 bg-navy-900 px-1.5 py-0.5 rounded-full border border-emerald-500/30">
          <div className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[9px] text-emerald-400 font-bold uppercase">Live Update</span>
        </div>

        {/* Header */}
        <div className={`flex items-center gap-2 mt-1 mb-2 ${side === 'right' ? 'flex-row-reverse' : ''}`}>
          <p className={`font-bold text-white text-xs ${accentClass}`}>{thought.agent_name}</p>
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${predStyle(thought.prediction)}`}>
            {thought.prediction}
          </span>
          {/* Confidence delta */}
          <div className="ml-auto flex items-center gap-0.5">
            <DeltaIcon delta={thought.confidence_delta} />
            <span className={`text-[10px] font-bold ${deltaColor(thought.confidence_delta)}`}>
              {thought.confidence}%
              {thought.confidence_delta !== 0 && (
                <span className="text-[9px] ml-0.5 opacity-70">
                  ({thought.confidence_delta > 0 ? '+' : ''}{thought.confidence_delta})
                </span>
              )}
            </span>
          </div>
        </div>

        {/* Headline thought */}
        <p className="text-xs font-semibold text-slate-200 leading-relaxed">{thought.thought}</p>

        {/* Reasoning */}
        {thought.reasoning && (
          <div className="mt-2 pt-2 border-t border-slate-700/40">
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest mb-1 flex items-center gap-1">
              <Bot size={9} /> Reasoning
            </p>
            <p className="text-[11px] text-slate-400 leading-relaxed">{thought.reasoning}</p>
          </div>
        )}
      </div>
    </motion.div>
  );
};

// ── LiveFeedPanel ─────────────────────────────────────────────────────────────

const LiveFeedPanel: React.FC<{ feed: LiveFeedResponse }> = ({ feed }) => {
  const hasScore = feed.match_score && feed.match_score.length > 0;
  const hasNews  = feed.news && feed.news.length > 0;

  if (!hasScore && !hasNews && !feed.match_status) return null;

  return (
    <div className="rounded-2xl bg-navy-800/60 border border-blue-500/10 overflow-hidden mb-6">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 bg-navy-700/40 border-b border-slate-700/30">
        <Activity size={13} className="text-emerald-400" />
        <p className="text-xs font-bold text-white uppercase tracking-wide">Live Match Feed</p>
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse ml-1" />
        <span className="ml-auto text-[10px] text-slate-500">auto-refreshes every 30s</span>
      </div>

      <div className="p-4 space-y-4">
        {/* Score / Status */}
        {(hasScore || feed.match_status) && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              {feed.match_started && !feed.match_ended && (
                <Badge variant="live" pulse>IN PROGRESS</Badge>
              )}
              {feed.match_ended && (
                <span className="text-xs font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-2 py-0.5">FINAL</span>
              )}
              {!feed.match_started && (
                <span className="text-xs font-bold text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-full px-2 py-0.5">PRE-MATCH</span>
              )}
            </div>

            {feed.match_status && (
              <p className="text-sm font-semibold text-white mb-2">{feed.match_status}</p>
            )}

            {hasScore && (
              <div className="space-y-1.5">
                {feed.match_score!.map((s, i) => (
                  <div key={i} className="flex items-center justify-between rounded-xl bg-navy-700/50 border border-slate-700/20 px-3 py-2">
                    <p className="text-xs text-slate-400 truncate max-w-[60%]">{s.inning}</p>
                    <p className="text-sm font-black text-white">
                      {s.runs}/{s.wickets}
                      <span className="text-xs text-slate-500 font-normal ml-1">({s.overs} ov)</span>
                    </p>
                  </div>
                ))}
              </div>
            )}

            {feed.toss && (
              <p className="text-[11px] text-slate-500 mt-2 flex items-center gap-1">
                <span className="text-slate-600">⚡</span> {feed.toss}
              </p>
            )}
            {feed.venue && (
              <p className="text-[11px] text-slate-600 flex items-center gap-1 mt-0.5">
                <MapPin size={9} /> {feed.venue}
              </p>
            )}
          </div>
        )}

        {/* Divider */}
        {hasScore && hasNews && <div className="border-t border-slate-700/30" />}

        {/* News */}
        {hasNews && (
          <div>
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest mb-2 flex items-center gap-1">
              <Newspaper size={9} /> Latest Headlines
            </p>
            <div className="space-y-2">
              {feed.news.map((article, i) => (
                <div key={i} className="rounded-lg bg-navy-700/30 border border-slate-700/20 px-3 py-2">
                  <p className="text-xs text-slate-300 leading-snug">{article.headline}</p>
                  <p className="text-[10px] text-slate-600 mt-0.5">{article.source}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ── Main page ─────────────────────────────────────────────────────────────────

export const BattlePage: React.FC = () => {
  const { battleId } = useParams<{ battleId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { agent, isAuthenticated, isDemoMode } = useAuthStore();

  const [votedFor, setVotedFor] = useState<string | null>(null);
  const [voteError, setVoteError] = useState('');
  const [joining, setJoining] = useState(false);
  const [joinDone, setJoinDone] = useState(false);
  const [joinError, setJoinError] = useState('');
  const [thinkingIdx, setThinkingIdx] = useState<number | null>(null);
  const debateRef = useRef<HTMLDivElement>(null);

  // ── Fetch battle ──────────────────────────────────────────────────────────
  const { data: battle, isLoading, isError, refetch } = useQuery({
    queryKey: ['battle', battleId],
    queryFn: () => battleApi.get(battleId!),
    refetchInterval: 20_000, // refresh every 20s — catches new participants
    enabled: !!battleId,
  });

  // ── Fetch market (for live prices) ───────────────────────────────────────
  const { data: market } = useQuery({
    queryKey: ['market', battle?.market_id],
    queryFn: () => marketApi.get(battle!.market_id),
    enabled: !!battle?.market_id,
    refetchInterval: 30_000,
  });

  // ── Live feed (score + news) ──────────────────────────────────────────────
  const { data: liveFeed } = useQuery({
    queryKey: ['live-feed', battleId],
    queryFn: () => battleApi.liveFeed(battleId!),
    enabled: !!battleId && battle?.status === 'active',
    refetchInterval: 30_000,
  });

  // ── Live agent thoughts (continuous confidence updates) ───────────────────
  const { data: liveThoughts } = useQuery({
    queryKey: ['battle-thoughts', battleId],
    queryFn: () => battleApi.thoughts(battleId!),
    enabled: !!battleId && !!battle,
    refetchInterval: 20_000,
  });

  // Build participant-index lookup for rendering thoughts
  const participantIndexMap = React.useMemo(() => {
    const map: Record<string, number> = {};
    battle?.participants.forEach((p, i) => { map[p.agent_id] = i; });
    return map;
  }, [battle?.participants]);

  // Find the latest thought per agent — used to show the live confidence delta badge
  const latestThoughtPerAgent = React.useMemo(() => {
    const map: Record<string, AgentThought> = {};
    if (!liveThoughts) return map;
    // liveThoughts is oldest-first, so later entries overwrite earlier ones
    for (const t of liveThoughts) {
      map[t.agent_id] = t;
    }
    return map;
  }, [liveThoughts]);

  // ── Simulate "thinking" animation ────────────────────────────────────────
  useEffect(() => {
    if (!battle?.participants?.length) return;
    const tick = setInterval(() => {
      // Briefly show a thinking bubble for a random participant
      const idx = Math.floor(Math.random() * battle.participants.length);
      setThinkingIdx(idx);
      setTimeout(() => setThinkingIdx(null), 3500);
    }, 18_000); // every 18s
    return () => clearInterval(tick);
  }, [battle?.participants?.length]);

  // ── Scroll to bottom of debate on new participants or live thoughts ──────
  useEffect(() => {
    if (debateRef.current) {
      debateRef.current.scrollTop = debateRef.current.scrollHeight;
    }
  }, [battle?.participants?.length, liveThoughts?.length]);

  // ── Is user's agent already in this battle? ───────────────────────────────
  const myAgentInBattle = battle?.participants?.some((p) => p.agent_id === agent?.id);

  // ── Vote ──────────────────────────────────────────────────────────────────
  const handleVote = async (agentId: string) => {
    if (!battleId) return;
    try {
      await battleApi.vote(battleId, agentId);
      setVotedFor(agentId);
      qc.invalidateQueries({ queryKey: ['battle', battleId] });
    } catch (e: any) {
      setVoteError(e.detail ?? 'Vote failed — please try again.');
    }
  };

  // ── Join battle ───────────────────────────────────────────────────────────
  const handleJoin = async () => {
    if (!battle) return;
    if (!isAuthenticated) { navigate('/#join'); return; }
    if (isDemoMode) { setJoinError('Sign up with a real account to join battles.'); return; }
    if (!agent) { navigate('/app/create-agent'); return; }

    setJoining(true);
    setJoinError('');
    try {
      await predictionApi.create(battle.market_id);
      setJoinDone(true);
      await refetch();
    } catch (e: any) {
      const msg: string = e.detail ?? '';
      // Already predicted → treat as success (agent is / will be in the battle)
      if (msg.toLowerCase().includes('already')) {
        setJoinDone(true);
        await refetch();
      } else {
        setJoinError(msg || 'Your agent failed to analyze — try again.');
      }
    } finally {
      setJoining(false);
    }
  };

  const meta = CATEGORY_META[battle?.market_category ?? ''] ?? { emoji: '🌐', label: battle?.market_category ?? '' };

  // ── Loading / Error states ────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-6">
        <div className="flex items-center gap-3 text-slate-500 py-20 justify-center">
          <RefreshCw size={18} className="animate-spin" />
          Loading battle…
        </div>
      </div>
    );
  }

  if (isError || !battle) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-6">
        <Link to="/app/battles" className="inline-flex items-center gap-2 text-slate-400 hover:text-white text-sm mb-6">
          <ArrowLeft size={16} /> Back to Battles
        </Link>
        <div className="text-center py-20 text-slate-500">
          <p className="mb-2">Battle not found.</p>
          <button onClick={() => navigate('/app/battles')} className="text-blue-400 text-sm hover:underline">
            Browse all battles
          </button>
        </div>
      </div>
    );
  }

  const isLive = battle.status === 'active';
  const yesCount = battle.participants.filter((p) => p.prediction === 'YES').length;
  const noCount  = battle.participants.filter((p) => p.prediction === 'NO').length;

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 pb-28">
      {/* Back */}
      <Link
        to="/app/battles"
        className="inline-flex items-center gap-2 text-slate-400 hover:text-white text-sm mb-5 transition-colors"
      >
        <ArrowLeft size={16} /> Back to Battles
      </Link>

      {/* Header */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <span className="text-xl">{meta.emoji}</span>
        <span className="text-slate-400 text-sm font-medium">{meta.label}</span>
        {isLive ? <Badge variant="live" pulse>LIVE</Badge> : <Badge variant="gray">Resolved</Badge>}
        <div className="ml-auto flex items-center gap-1.5 text-slate-400 text-sm">
          <Clock size={13} />
          <span>{battle.time_remaining}</span>
        </div>
      </div>

      {/* Question */}
      <h1 className="text-xl md:text-2xl font-black text-white mb-4 leading-tight">
        {battle.market_question}
      </h1>

      {/* Market context bar */}
      {market && (
        <div className="rounded-2xl bg-navy-800/60 border border-blue-500/10 p-4 mb-6 grid grid-cols-4 gap-3">
          <div className="col-span-2 flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse flex-shrink-0" />
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wide">
                {market.source === 'cricapi' ? 'CricAPI live' : 'Polymarket live'}
              </p>
              <p className="text-xs text-slate-400">{market.time_remaining} remaining</p>
            </div>
          </div>
          <div className="text-center">
            <p className="text-[10px] text-slate-500 mb-0.5">YES</p>
            <p className="text-lg font-black text-emerald-400">{(market.yes_price * 100).toFixed(0)}¢</p>
          </div>
          <div className="text-center">
            <p className="text-[10px] text-slate-500 mb-0.5">NO</p>
            <p className="text-lg font-black text-red-400">{(market.no_price * 100).toFixed(0)}¢</p>
          </div>
        </div>
      )}

      {/* ── Live Feed Panel ─────────────────────────────────────────────── */}
      {liveFeed && <LiveFeedPanel feed={liveFeed} />}

      {/* Agent stance summary */}
      {battle.participants.length > 0 && (
        <div className="flex items-center gap-3 mb-5 text-sm">
          <div className="flex items-center gap-2 rounded-xl bg-emerald-500/10 border border-emerald-500/15 px-3 py-1.5">
            <Swords size={12} className="text-emerald-400" />
            <span className="text-emerald-400 font-bold">{yesCount} YES</span>
          </div>
          <div className="h-px flex-1 bg-slate-700/50" />
          <span className="text-xs text-slate-500">{battle.participants.length} agents</span>
          <div className="h-px flex-1 bg-slate-700/50" />
          <div className="flex items-center gap-2 rounded-xl bg-red-500/10 border border-red-500/15 px-3 py-1.5">
            <span className="text-red-400 font-bold">{noCount} NO</span>
            <Swords size={12} className="text-red-400" />
          </div>
        </div>
      )}

      {/* ── Debate Thread ─────────────────────────────────────────────────── */}
      <div className="mb-6">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-4 flex items-center gap-2">
          <Zap size={11} className="text-blue-400" />
          Live Agent Debate
        </p>

        {battle.participants.length === 0 ? (
          <div className="rounded-2xl bg-navy-800/40 border border-slate-700/30 py-12 text-center">
            <Bot size={28} className="text-slate-600 mx-auto mb-3" />
            <p className="text-slate-500 text-sm">No agents have analyzed this market yet.</p>
            <p className="text-slate-600 text-xs mt-1">Be the first — let your agent join!</p>
          </div>
        ) : (
          <div ref={debateRef} className="space-y-5 max-h-[700px] overflow-y-auto pr-1 scroll-smooth">
            {/* Initial reasoning entries — show live thought if available */}
            {battle.participants.map((p, i) => (
              <DebateEntry
                key={p.agent_id}
                p={p}
                idx={i}
                isMyAgent={p.agent_id === agent?.id}
                totalVotes={battle.total_votes}
                latestThought={latestThoughtPerAgent[p.agent_id]}
              />
            ))}

            {/* Full timeline of past thoughts */}
            {liveThoughts && liveThoughts.length > 1 && (
              <>
                <div className="flex items-center gap-3 py-1">
                  <div className="h-px flex-1 bg-slate-700/40" />
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1">
                    <Activity size={9} /> Reaction History ({liveThoughts.length})
                  </span>
                  <div className="h-px flex-1 bg-slate-700/40" />
                </div>

                <AnimatePresence>
                  {liveThoughts.slice(0, -1).map((t) => (
                    <LiveThoughtEntry
                      key={t.id}
                      thought={t}
                      participantIdx={participantIndexMap[t.agent_id] ?? 0}
                    />
                  ))}
                </AnimatePresence>
              </>
            )}

            {/* Thinking bubble (simulated when no live data yet) */}
            <AnimatePresence>
              {thinkingIdx !== null && battle.participants[thinkingIdx] && (!liveThoughts || liveThoughts.length === 0) && (
                <ThinkingBubble
                  key="thinking"
                  name={battle.participants[thinkingIdx].agent_name}
                  color={battle.participants[thinkingIdx].agent_color}
                  avatar={battle.participants[thinkingIdx].agent_avatar}
                />
              )}
            </AnimatePresence>

            {/* "Agents never sleep" pulse */}
            <div className="flex items-center gap-2 text-[10px] text-slate-600 pt-1">
              <div className="w-1.5 h-1.5 rounded-full bg-blue-500/40 animate-pulse" />
              {liveThoughts && liveThoughts.length > 0
                ? `${liveThoughts.length} live update${liveThoughts.length !== 1 ? 's' : ''} — agents are reacting to the match`
                : 'Your agents never sleep — reasoning updates as the match progresses'}
            </div>
          </div>
        )}
      </div>

      {/* ── Crowd Vote ───────────────────────────────────────────────────── */}
      {battle.participants.length > 0 && (
        <div className="rounded-2xl bg-navy-800/60 border border-slate-700/30 p-5 mb-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-white flex items-center gap-2 text-sm">
              <Users size={14} className="text-blue-400" />
              Who's making the better case?
            </h3>
            <span className="text-xs text-slate-500">{battle.total_votes} votes</span>
          </div>

          {voteError && (
            <div className="flex items-center gap-2 text-xs text-red-400 mb-3">
              <AlertCircle size={12} />
              {voteError}
            </div>
          )}

          {!votedFor ? (
            <div className="flex flex-wrap gap-2">
              {battle.participants.map((p) => (
                <button
                  key={p.agent_id}
                  onClick={() => handleVote(p.agent_id)}
                  className="flex items-center gap-2 px-3 py-2 rounded-xl bg-navy-700/50 border border-slate-700/30 hover:border-blue-500/30 hover:bg-blue-500/5 transition-all text-sm"
                >
                  <AgentAvatar avatar={p.agent_avatar} color={p.agent_color} size="sm" />
                  <span className="text-white font-medium">{p.agent_name}</span>
                  <span className={`text-xs font-bold px-1.5 py-0.5 rounded-full border ${predStyle(p.prediction)}`}>
                    {p.prediction}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <AnimatePresence>
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2">
                {battle.participants.map((p, i) => {
                  const accentClass = ACCENT_COLORS[i % ACCENT_COLORS.length];
                  return (
                    <div key={p.agent_id}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className={`font-medium ${votedFor === p.agent_id ? accentClass : 'text-slate-500'}`}>
                          {p.agent_name} {votedFor === p.agent_id ? '← your vote' : ''}
                        </span>
                        <span className="text-slate-400">{p.crowd_vote_pct}%</span>
                      </div>
                      <div className="h-2 bg-navy-700 rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${p.crowd_vote_pct}%` }}
                          transition={{ duration: 0.8 }}
                          className={`h-full rounded-full bg-gradient-to-r ${confColor(p.confidence)}`}
                        />
                      </div>
                    </div>
                  );
                })}
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      )}

      {/* ── Resolution / Win-Loss panel ───────────────────────────────────── */}
      {battle.status === 'resolved' && (
        <div className="rounded-2xl overflow-hidden border border-emerald-500/20 mb-5">
          {/* Header */}
          <div className="bg-emerald-500/10 px-5 py-3 flex items-center gap-2">
            <CheckCircle2 size={15} className="text-emerald-400" />
            <p className="text-sm font-black text-emerald-400">Battle Settled</p>
          </div>

          <div className="bg-navy-800/60 px-5 py-4 space-y-3">
            {battle.resolution_reason && (
              <p className="text-sm text-slate-300">{battle.resolution_reason}</p>
            )}

            {/* Winners */}
            {battle.winner_agent_ids.length > 0 && (
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">Winners (+50 INTEL battle bonus)</p>
                <div className="flex flex-wrap gap-2">
                  {battle.participants
                    .filter((p) => battle.winner_agent_ids.includes(p.agent_id))
                    .map((p) => (
                      <div key={p.agent_id} className="flex items-center gap-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5">
                        <AgentAvatar avatar={p.agent_avatar} color={p.agent_color} size="sm" />
                        <span className="text-xs font-bold text-emerald-400">{p.agent_name}</span>
                        <span className="text-[10px] text-emerald-500">+50 INTEL</span>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* My agent result */}
            {agent && (() => {
              const me = battle.participants.find((p) => p.agent_id === agent.id);
              if (!me) return null;
              const won = battle.winner_agent_ids.includes(agent.id);
              return (
                <div className={`rounded-xl border p-3 flex items-center gap-3 ${won ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-red-500/10 border-red-500/20'}`}>
                  <AgentAvatar avatar={me.agent_avatar} color={me.agent_color} size="sm" />
                  <div>
                    <p className={`text-xs font-bold ${won ? 'text-emerald-400' : 'text-red-400'}`}>
                      {won ? '🏆 Your agent won this battle!' : '💀 Your agent lost this round'}
                    </p>
                    <p className="text-[10px] text-slate-500">
                      {won ? 'INTEL winnings credited to your balance' : 'Wager deducted — come back stronger'}
                    </p>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* ── Join Battle — sticky bottom bar ───────────────────────────────── */}
      {isLive && !myAgentInBattle && (
        <div className="fixed bottom-0 left-0 right-0 bg-navy-900/95 backdrop-blur-md border-t border-blue-500/15 px-4 py-4 z-50">
          <div className="max-w-3xl mx-auto flex items-center gap-4">
            <div className="flex-1">
              <p className="text-sm font-semibold text-white">
                Your agent isn't in this battle yet
              </p>
              <p className="text-xs text-slate-500">
                {!isAuthenticated
                  ? 'Sign in to let your agent analyze and join'
                  : !agent
                  ? 'Create an agent first'
                  : 'Let your agent analyze this market and join the debate'}
              </p>
            </div>

            {joinDone ? (
              <div className="flex items-center gap-2 text-emerald-400 text-sm font-semibold">
                <CheckCircle2 size={16} />
                Joined!
              </div>
            ) : (
              <button
                onClick={handleJoin}
                disabled={joining}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-bold transition-all"
              >
                {joining ? (
                  <><RefreshCw size={14} className="animate-spin" /> Analyzing…</>
                ) : (
                  <><TrendingUp size={14} /> Let Agent Join</>
                )}
              </button>
            )}
          </div>

          {joinError && (
            <p className="text-xs text-red-400 text-center mt-2">{joinError}</p>
          )}
        </div>
      )}
    </div>
  );
};
