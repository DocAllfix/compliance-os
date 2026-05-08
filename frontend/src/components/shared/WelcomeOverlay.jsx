import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { UploadCloud, BarChart2, ArrowRight, X, FileSearch } from 'lucide-react';

const STORAGE_KEY = 'compliance-os-welcome-count';
const MAX_SHOWS = 3;

const steps = [
  { icon: UploadCloud,  num: '①', text: 'Upload your company documents as a ZIP archive',     color: 'text-primary' },
  { icon: FileSearch,   num: '②', text: 'AI analyses conformance gaps against ISO standards',  color: 'text-success' },
  { icon: BarChart2,    num: '③', text: 'Review findings, track NCRs, download your report',   color: 'text-info'    },
];

export default function WelcomeOverlay({ user }) {
  const [visible, setVisible] = useState(false);
  const navigate = useNavigate();
  const prefersReduced = useReducedMotion();

  useEffect(() => {
    const count = parseInt(localStorage.getItem(STORAGE_KEY) || '0', 10);
    if (count < MAX_SHOWS) {
      localStorage.setItem(STORAGE_KEY, String(count + 1));
      setVisible(true);
    }
  }, []);

  const firstName = user?.full_name
    ? user.full_name.trim().split(' ')[0]
    : (user?.username || null);

  const dismiss = () => setVisible(false);

  const start = () => {
    dismiss();
    navigate('/new-analysis');
  };

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key="overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4"
        >
          <motion.div
            initial={{ opacity: 0, scale: prefersReduced ? 1 : 0.96, y: prefersReduced ? 0 : 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: prefersReduced ? 1 : 0.96, y: prefersReduced ? 0 : 12 }}
            transition={{ duration: prefersReduced ? 0 : 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="relative max-w-md w-full rounded-2xl border border-border bg-card p-8"
          >
            <button
              onClick={dismiss}
              className="absolute top-4 right-4 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>

            {/* Logo + Title */}
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-xl brand-gradient flex items-center justify-center shrink-0">
                <span className="text-white font-bold font-mono">C</span>
              </div>
              <div>
                <h2 className="text-lg font-bold tracking-tight leading-tight">
                  {firstName ? `Welcome, ${firstName}` : 'Welcome'} to ComplianceOS
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">ISO 9001 · 14001 · 45001 gap analysis</p>
              </div>
            </div>

            <p className="text-sm text-muted-foreground mt-5 mb-4">Get started in three steps:</p>

            <div className="space-y-3 mb-7">
              {steps.map(({ icon: Icon, num, text, color }, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: prefersReduced ? 0 : -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: prefersReduced ? 0 : 0.15 + i * 0.08 }}
                  className="flex items-center gap-3"
                >
                  <div className={`w-8 h-8 rounded-lg bg-muted/50 flex items-center justify-center shrink-0 text-sm font-bold ${color}`}>
                    {num}
                  </div>
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <Icon className={`w-4 h-4 shrink-0 ${color}`} />
                    <span className="text-sm">{text}</span>
                  </div>
                </motion.div>
              ))}
            </div>

            <div className="flex flex-col gap-2">
              <Button onClick={start} className="w-full font-semibold h-11 gap-2">
                <ArrowRight className="w-4 h-4" />
                Start a New Analysis
              </Button>
              <Button onClick={dismiss} variant="ghost" className="w-full text-muted-foreground text-sm h-9">
                Dismiss — explore the app
              </Button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
