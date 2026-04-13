import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Clock, TrendingUp, Bot, ChevronDown, Swords, AlertCircle, CheckCircle2 } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { AgentAvatar } from '../ui/AgentAvatar';
import { useTypewriter } from '../../hooks/useTypewriter';
import { useAuthStore } from '../../stores/authStore';
import { predictionApi, type PredictionApiResponse } from '../../lib/api';

interface Market {
  id: string;           // external_id — used as market_id in prediction
  source: string;       // "polymarket" | "cricapi"
  question: string;
  yesPrice: number;
  noPrice: number;
  volume: string;
  timeRemaining: string;
  category: string;
  categoryEmoji: string;
  closingSoon: boolean;
}

type AnalyzeState = 'idle' | 'thinking' | 'done' | 'error';

// Thinking steps shown while agent runs
const THINKING_STEPS = [
  '🔍 Reading live market signals…',
  '📰 Scanning latest news…',
  '📊 Evaluating crowd sentiment…',
  '🧠 Forming prediction…',
];

const ThinkingDots: React.FC<{ step: string }> = ({ step }) => (
  <motion.div
    key={step}
    initial={{ opacity: 0, x: -4 }}
    animate={{ opacity: 1, x: 0 }}
    exit={{ opacity: 0 }}
    className="flex items-center gap-2 text-xs text-blue-400"
  >
    <span>{step}</span>
    <span className="flex gap-0.5">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ repeat: Infinity, duration: 1.2, delay: i * 0.2 }}
          className="w-1 h-1 bg-blue-400 rounded-full block"
        />
      ))}
    </span>
  </motion.div>
);

export const MarketCard: React.FC<{ market: Market }> = ({ market }) => {
  const [state, setState] = useState<AnalyzeState>('idle');
  const [prediction, setPrediction] = useState<PredictionApiResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [showReasoning, setShowReasoning] = useState(false);
  const [thinkingStep, setThinkingStep] = useState(0);
  const { agent, isAuthenticated, isDemoMode } = useAuthStore();
  const navigate = useNavigate();

  const { displayed, isDone } = useTypewriter(
    prediction?.reasoning_text ?? '',
    12,
    showReasoning && !!prediction,
  );

  const handleAnalyze = async () => {
    if (!isAuthenticated) {
      navigate('/#join');
      return;
    }
    if (isDemoMode) {
      setErrorMsg('Demo mode — sign up with a real account to let your agent make live predictions.');
      setState('error');
      return;
    }
    if (!agent) {
      navigate('/app/create-agent');
      return;
    }

    setState('thinking');
    setErrorMsg('');
    setPrediction(null);
    setShowReasoning(false);

    // Cycle through thinking steps while we wait
    let stepIdx = 0;
    const stepTimer = setInterval(() => {
      stepIdx = Math.min(stepIdx + 1, THINKING_STEPS.length - 1);
      setThinkingStep(stepIdx);
    }, 2200);

    try {
      const result = await predictionApi.create(market.id);
      clearInterval(stepTimer);
      setPrediction(result);
      setState('done');
      setShowReasoning(true);
    } catch (e: any) {
      clearInterval(stepTimer);
      setErrorMsg(e.detail ?? 'Analysis failed. Try again.');
      setState('error');
    }
  };

  const yesColor =
    market.yesPrice >= 0.6
      ? 'text-emerald-400'
      : market.yesPrice <= 0.4
      ? 'text-red-400'
      : 'text-amber-400';

  const predColor =
    prediction?.predicted_outcome === 'YES' ? 'text-emerald-400' : 'text-red-400';
  const predBg =
    prediction?.predicted_outcome === 'YES'
      ? 'bg-emerald-500/10 border-emerald-500/20'
      : 'bg-red-500/10 border-red-500/20';

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={state === 'idle' ? { y: -2 } : {}}
      className="rounded-2xl border border-blue-500/10 bg-navy-800/60 backdrop-blur-sm p-5 transition-all duration-300 hover:border-blue-500/25 hover:shadow-[0_0_25px_rgba(59,130,246,0.06)]"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-start gap-2 flex-1">
          <span>{market.categoryEmoji}</span>
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-white leading-snug">{market.question}</p>
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant={market.category === 'IPL 2026' ? 'blue' : 'red'} size="sm">
                {market.category}
              </Badge>
              {market.closingSoon && <Badge variant="amber" size="sm">Closing Soon</Badge>}
            </div>
          </div>
        </div>
      </div>

      {/* Price grid */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="rounded-xl bg-emerald-500/5 border border-emerald-500/15 p-3 text-center">
          <p className="text-xs text-slate-500 mb-1">YES</p>
          <p className={`text-lg font-bold ${yesColor}`}>{(market.yesPrice * 100).toFixed(0)}¢</p>
        </div>
        <div className="rounded-xl bg-red-500/5 border border-red-500/15 p-3 text-center">
          <p className="text-xs text-slate-500 mb-1">NO</p>
          <p className="text-lg font-bold text-red-400">{(market.noPrice * 100).toFixed(0)}¢</p>
        </div>
        <div className="rounded-xl bg-navy-700/50 border border-slate-700/30 p-3 text-center">
          <p className="text-xs text-slate-500 mb-1">Volume</p>
          <p className="text-sm font-bold text-slate-300">{market.volume}</p>
        </div>
      </div>

      {/* Time + source */}
      <div className="flex items-center gap-1.5 text-xs text-slate-500 mb-4">
        <Clock size={12} />
        <span>{market.timeRemaining} remaining</span>
        <span className="text-slate-700 mx-1">·</span>
        <TrendingUp size={12} />
        {market.source === 'cricapi' ? (
          <span className="text-amber-400 font-medium">CricAPI live</span>
        ) : (
          <span>Polymarket live</span>
        )}
      </div>

      {/* ── Analyze button ── */}
      {state === 'idle' && (
        <Button
          variant="secondary"
          size="sm"
          className="w-full"
          icon={<Bot size={14} />}
          onClick={handleAnalyze}
        >
          {!isAuthenticated
            ? 'Sign in to Let Agent Analyze'
            : isDemoMode
            ? 'Sign Up to Use Real Analysis'
            : !agent
            ? 'Create Agent to Analyze'
            : 'Let My Agent Analyze This'}
        </Button>
      )}

      {/* ── Thinking state ── */}
      {state === 'thinking' && (
        <div className="rounded-xl bg-blue-500/5 border border-blue-500/15 p-4">
          <div className="flex items-center gap-2 mb-3">
            {agent && (
              <AgentAvatar
                avatar={agent.avatar_id}
                color={agent.color_theme}
                size="sm"
              />
            )}
            <p className="text-xs font-semibold text-blue-400">
              {agent?.name ?? 'Your Agent'} is analyzing…
            </p>
          </div>
          <div className="space-y-1.5">
            {THINKING_STEPS.slice(0, thinkingStep + 1).map((step, i) => (
              <ThinkingDots key={i} step={step} />
            ))}
          </div>
          <p className="text-xs text-slate-600 mt-3">
            This usually takes 5–15 seconds
          </p>
        </div>
      )}

      {/* ── Error state ── */}
      {state === 'error' && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/20 p-4 flex items-start gap-2">
          <AlertCircle size={14} className="text-red-400 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-xs text-red-400">{errorMsg}</p>
            <button
              onClick={() => setState('idle')}
              className="text-xs text-slate-500 hover:text-slate-300 mt-1 transition-colors"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {/* ── Result ── */}
      <AnimatePresence>
        {state === 'done' && prediction && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3 }}
            className="space-y-3"
          >
            {/* Prediction summary */}
            <div className={`rounded-xl border p-3 flex items-center gap-3 ${predBg}`}>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-0.5">
                  <CheckCircle2 size={13} className="text-emerald-400" />
                  <p className="text-xs font-semibold text-white">
                    {agent?.name ?? 'Agent'} placed a bet
                  </p>
                </div>
                <p className="text-xs text-slate-400">
                  Wagered <span className="text-white font-bold">{prediction.intel_wagered} INTEL</span>
                </p>
              </div>
              <div className="text-right">
                <p className={`text-xl font-black ${predColor}`}>
                  {prediction.predicted_outcome}
                </p>
                <p className="text-xs text-slate-400">{prediction.confidence_score}% confident</p>
              </div>
            </div>

            {/* Reasoning */}
            {showReasoning && (
              <div className="rounded-xl bg-navy-700/40 border border-slate-700/30 p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-blue-400 flex items-center gap-1">
                    <Bot size={12} />
                    Agent Reasoning
                  </p>
                  <button
                    onClick={() => setShowReasoning(!showReasoning)}
                    className="text-slate-500 hover:text-slate-300 transition-colors"
                  >
                    <ChevronDown size={14} />
                  </button>
                </div>
                {prediction.key_signal && (
                  <p className="text-[10px] text-amber-400 font-semibold mb-2 uppercase tracking-wide">
                    Key Signal: {prediction.key_signal}
                  </p>
                )}
                <p className={`text-xs text-slate-300 leading-relaxed ${!isDone ? 'typewriter-cursor' : ''}`}>
                  {displayed}
                </p>
              </div>
            )}

            {/* Go to battle */}
            <button
              onClick={() => navigate('/app/battles')}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-semibold hover:bg-blue-500/15 transition-all group"
            >
              <Swords size={13} className="group-hover:scale-110 transition-transform" />
              View in Battle Feed →
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};
