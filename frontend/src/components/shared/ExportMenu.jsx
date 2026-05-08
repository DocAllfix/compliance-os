import React, { useState } from 'react';
import { Download, FileText, FileSpreadsheet, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator, DropdownMenuLabel
} from '@/components/ui/dropdown-menu';
import { jsPDF } from 'jspdf';
import * as XLSX from 'xlsx';
import { format } from 'date-fns';
import { enGB } from 'date-fns/locale';

// Export a single practice — just download its file_url if available
// or generate a PDF summary card
async function exportSinglePDF(practice) {
  if (practice.file_url && practice.type !== 'checklist_json') {
    window.open(practice.file_url, '_blank');
    return;
  }

  const doc = new jsPDF();
  doc.setFontSize(20);
  doc.text('Analysis Detail', 20, 20);
  doc.setFontSize(11);
  doc.setTextColor(100);
  doc.text(`Generated: ${format(new Date(), 'dd/MM/yyyy HH:mm', { locale: enGB })}`, 20, 30);

  doc.setDrawColor(180);
  doc.line(20, 34, 190, 34);

  const rows = [
    ['Company', practice.company_name || '—'],
    ['Type', practice.type || '—'],
    ['Standard', practice.norm || '—'],
    ['Status', practice.status || '—'],
    ['Date', practice.created_date ? format(new Date(practice.created_date), 'dd/MM/yyyy HH:mm', { locale: enGB }) : '—'],
    ['Processing time', practice.processing_time_seconds ? `${practice.processing_time_seconds}s` : '—'],
    ['Total clauses', practice.clauses_total ?? '—'],
    ['Complete clauses', practice.clauses_complete ?? '—'],
  ];

  let y = 44;
  doc.setTextColor(0);
  rows.forEach(([label, value]) => {
    doc.setFont(undefined, 'bold');
    doc.text(`${label}:`, 20, y);
    doc.setFont(undefined, 'normal');
    doc.text(String(value), 75, y);
    y += 10;
  });

  if (practice.error_message) {
    y += 4;
    doc.setTextColor(200, 50, 50);
    doc.text('Error:', 20, y);
    doc.setTextColor(0);
    doc.setFont(undefined, 'normal');
    const lines = doc.splitTextToSize(practice.error_message, 120);
    doc.text(lines, 75, y);
  }

  doc.save(`analysis_${practice.company_name?.replace(/\s+/g, '_') || practice.id}.pdf`);
}

function exportListPDF(practices) {
  const doc = new jsPDF({ orientation: 'landscape' });
  doc.setFontSize(16);
  doc.text('Analysis History', 14, 16);
  doc.setFontSize(9);
  doc.setTextColor(120);
  doc.text(`Exported: ${format(new Date(), 'dd/MM/yyyy HH:mm', { locale: enGB })} — ${practices.length} record${practices.length !== 1 ? 's' : ''}`, 14, 22);

  doc.setTextColor(0);
  doc.setFontSize(9);

  const headers = ['#', 'Company', 'Type', 'Standard', 'Status', 'Date', 'Time (s)', 'Clauses'];
  const colX =     [14,   30,        80,     120,    150,    175,    220,          248];

  // Header row
  let y = 30;
  doc.setFont(undefined, 'bold');
  headers.forEach((h, i) => doc.text(h, colX[i], y));
  doc.setFont(undefined, 'normal');
  doc.setDrawColor(180);
  doc.line(14, y + 2, 280, y + 2);
  y += 8;

  practices.forEach((p, idx) => {
    if (y > 190) { doc.addPage(); y = 20; }
    const row = [
      String(idx + 1),
      p.company_name || '—',
      p.type || '—',
      p.norm || '—',
      p.status || '—',
      p.created_date ? format(new Date(p.created_date), 'dd/MM/yy', { locale: enGB }) : '—',
      p.processing_time_seconds ? String(p.processing_time_seconds) : '—',
      p.clauses_total ? `${p.clauses_complete ?? 0}/${p.clauses_total}` : '—',
    ];
    row.forEach((val, i) => {
      const text = doc.splitTextToSize(val, (colX[i + 1] || 280) - colX[i] - 2);
      doc.text(text, colX[i], y);
    });
    y += 7;
  });

  doc.save(`analysis_history_${format(new Date(), 'yyyyMMdd')}.pdf`);
}

function exportListExcel(practices) {
  const rows = practices.map((p, i) => ({
    '#': i + 1,
    'Company': p.company_name || '',
    'Type': p.type || '',
    'Standard': p.norm || '',
    'Status': p.status || '',
    'Date': p.created_date ? format(new Date(p.created_date), 'dd/MM/yyyy HH:mm', { locale: enGB }) : '',
    'Time (s)': p.processing_time_seconds || '',
    'Total Clauses': p.clauses_total || '',
    'Complete Clauses': p.clauses_complete || '',
    'Error': p.error_message || '',
    'File URL': p.file_url || '',
  }));

  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Analyses');
  XLSX.writeFile(wb, `analysis_history_${format(new Date(), 'yyyyMMdd')}.xlsx`);
}

/**
 * mode="single" -> shows PDF download button for one practice
 * mode="list"   -> shows dropdown with PDF/Excel export for a list of practices
 */
export default function ExportMenu({ mode = 'list', practice = null, practices = [] }) {
  const [loading, setLoading] = useState(false);

  if (mode === 'single') {
    return (
      <Button
        variant="ghost" size="icon" className="h-8 w-8"
        disabled={loading}
        onClick={async () => {
          setLoading(true);
          await exportSinglePDF(practice);
          setLoading(false);
        }}
        aria-label="Download analysis"
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
      </Button>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2" disabled={practices.length === 0}>
          <Download className="w-4 h-4" />
          Export list
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuLabel className="text-xs text-muted-foreground">
          {practices.length} record{practices.length !== 1 ? 's' : ''} selected
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => exportListPDF(practices)} className="gap-2 cursor-pointer">
          <FileText className="w-4 h-4 text-destructive" />
          Export PDF
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => exportListExcel(practices)} className="gap-2 cursor-pointer">
          <FileSpreadsheet className="w-4 h-4 text-success" />
          Export Excel
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}