// @ts-nocheck
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { HelpCircle, Clock, AlertCircle, FolderOpen, ClipboardCheck } from 'lucide-react';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const faqs = [
  { q: 'How long does processing take?', a: 'Processing time depends on the number of documents. On average: 30-90 seconds for a ZIP containing 20-50 files. Larger ZIPs may take up to 3-5 minutes.' },
  { q: 'Why are some clauses empty?', a: 'The AI may not find evidence in the report for certain clauses. Use the "Recover Missing Clauses" function or fill them in manually from the detail drawer.' },
  { q: 'How do I correct the company name?', a: 'In the "Produce Checklist" tab, click the edit icon next to the detected company name. The change propagates to the JSON and the filename.' },
  { q: 'Can I process multiple analyses at once?', a: 'Currently the system processes one analysis at a time. You can start a new analysis as soon as the previous one has completed.' },
  { q: 'What should I do if the API is not responding?', a: 'Check your internet connection. The system has automatic recovery with up to 3 retry attempts. If the problem persists, contact support.' },
  { q: 'Which document formats are supported?', a: 'PDF, DOCX, DOC, XLSX, XLS, images (JPG, PNG, TIFF), email (.eml, .msg). Files are processed with OCR where necessary.' },
];

const problemButtons = [
  { icon: Clock, label: 'Slow processing', solution: 'Check the number of files in the ZIP. Reduce to fewer than 80 documents for optimal performance. The ZIP is processed in parallel batches.' },
  { icon: AlertCircle, label: 'Error', solution: 'Check the error log in the admin panel. API errors are recovered automatically. If the problem persists, try with a smaller file.' },
  { icon: FolderOpen, label: 'File will not upload', solution: 'Ensure the file is a valid ZIP format and does not exceed 500 MB. Verify that the ZIP is not password-protected.' },
  { icon: ClipboardCheck, label: 'Incomplete result', solution: 'Use the automatic recovery in tab 2. If some clauses remain empty, the original report may not contain the relevant documentation.' },
];

export default function Supporto() {
  const [activeProblem, setActiveProblem] = useState(null);

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <HelpCircle className="w-6 h-6 text-primary" /> Help & Support
        </h1>
        <p className="text-sm text-muted-foreground mt-1">Quick answers and guided diagnostics</p>
      </div>

      <Card className="glass">
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Frequently Asked Questions</CardTitle>
        </CardHeader>
        <CardContent>
          <Accordion type="single" collapsible className="space-y-1">
            {faqs.map((faq, i) => (
              <AccordionItem key={i} value={`faq-${i}`} className="border-b border-border/50">
                <AccordionTrigger className="text-sm font-medium hover:no-underline py-3">
                  {faq.q}
                </AccordionTrigger>
                <AccordionContent className="text-sm text-muted-foreground leading-relaxed pb-3">
                  {faq.a}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </CardContent>
      </Card>

      <Card className="glass">
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Guided Diagnostics</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">Select your issue:</p>
          <div className="flex flex-wrap gap-2">
            {problemButtons.map((pb) => {
              const Icon = pb.icon;
              return (
                <Button
                  key={pb.label}
                  variant={activeProblem === pb.label ? 'default' : 'outline'}
                  size="sm"
                  className={`text-xs gap-1.5 ${activeProblem === pb.label ? 'brand-gradient text-white' : ''}`}
                  onClick={() => setActiveProblem(activeProblem === pb.label ? null : pb.label)}
                >
                  <Icon className="w-3.5 h-3.5" /> {pb.label}
                </Button>
              );
            })}
          </div>
          {activeProblem && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="p-4 rounded-lg bg-muted/30 border">
              <p className="text-sm leading-relaxed">
                {problemButtons.find(pb => pb.label === activeProblem)?.solution}
              </p>
            </motion.div>
          )}
        </CardContent>
      </Card>

      <div className="text-center py-4">
        <p className="text-xs text-muted-foreground">Technical support: <span className="font-mono text-foreground">support@fiverise.co.uk</span></p>
      </div>
    </div>
  );
}
