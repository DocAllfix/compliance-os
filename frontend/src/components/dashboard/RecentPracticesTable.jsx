// @ts-nocheck
import React from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { enGB } from 'date-fns/locale';
import { Download, ArrowRight } from 'lucide-react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import StatusBadge from '@/components/shared/StatusBadge';
import EmptyState from '@/components/shared/EmptyState';
import { FileText } from 'lucide-react';

export default function RecentPracticesTable({ practices, isLoading }) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array(5).fill(0).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (!practices || practices.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="No analyses yet"
        description="Start a new analysis to see results here."
        action={
          <Link to="/new-analysis">
            <Button className="brand-gradient text-white">New Analysis</Button>
          </Link>
        }
      />
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Recent Analyses</h2>
        <Link to="/history" className="text-sm text-primary hover:text-primary/80 flex items-center gap-1 transition-colors">
          View all <ArrowRight className="w-3 h-3" />
        </Link>
      </div>
      <div className="rounded-lg border border-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30 hover:bg-muted/30">
              <TableHead className="text-xs font-semibold uppercase tracking-wider">Type</TableHead>
              <TableHead className="text-xs font-semibold uppercase tracking-wider">Company</TableHead>
              <TableHead className="text-xs font-semibold uppercase tracking-wider">Standard</TableHead>
              <TableHead className="text-xs font-semibold uppercase tracking-wider">Date</TableHead>
              <TableHead className="text-xs font-semibold uppercase tracking-wider">Time</TableHead>
              <TableHead className="text-xs font-semibold uppercase tracking-wider">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {practices.slice(0, 8).map((p) => (
              <TableRow key={p.id} className="hover:bg-muted/20 transition-colors">
                <TableCell><StatusBadge type={p.type} /></TableCell>
                <TableCell className="font-medium">{p.company_name}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{p.norm || '—'}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {p.created_date ? format(new Date(p.created_date), 'dd/MM HH:mm', { locale: enGB }) : '—'}
                </TableCell>
                <TableCell>
                  <span className={`text-sm font-mono ${
                    (p.processing_time_seconds || 0) < 60 ? 'text-success' :
                    (p.processing_time_seconds || 0) < 180 ? 'text-warning' : 'text-destructive'
                  }`}>
                    {p.processing_time_seconds ? `${p.processing_time_seconds}s` : '—'}
                  </span>
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    {p.file_url && (
                      <a href={p.file_url} target="_blank" rel="noopener noreferrer">
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <Download className="w-3.5 h-3.5" />
                        </Button>
                      </a>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
