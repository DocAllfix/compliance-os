// @ts-nocheck
import React from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { FileSearch, ArrowRight } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

const actions = [
  {
    path: '/new-analysis',
    icon: FileSearch,
    title: 'New Analysis',
    description: 'Upload documents and run an ISO gap analysis',
  },
];

export default function QuickActions() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {actions.map((a, i) => {
        const Icon = a.icon;
        return (
          <motion.div
            key={a.path}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.05 }}
          >
            <Link to={a.path}>
              <Card className="glass border-border hover:border-primary/30 hover:bg-primary/[0.03] transition-all duration-200 group cursor-pointer hover:-translate-y-0.5">
                <CardContent className="p-5">
                  <div className="p-2.5 rounded-lg bg-primary/10 w-fit mb-3">
                    <Icon className="w-5 h-5 text-primary" />
                  </div>
                  <h3 className="font-semibold text-sm mb-1">{a.title}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">{a.description}</p>
                  <div className="flex items-center gap-1 text-primary text-xs font-medium mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
                    Start <ArrowRight className="w-3 h-3" />
                  </div>
                </CardContent>
              </Card>
            </Link>
          </motion.div>
        );
      })}
    </div>
  );
}
