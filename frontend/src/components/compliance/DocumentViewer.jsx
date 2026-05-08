// @ts-nocheck
import React, { useState, useCallback, useEffect } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Maximize2, Minimize2, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

const ZOOM_STEPS = [0.6, 0.75, 0.9, 1.0, 1.25, 1.5, 2.0];

export default function DocumentViewer({ fileUrl, targetPages = [], onToggleExpand, isExpanded = false }) {
  const [numPages, setNumPages]     = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [zoomIdx, setZoomIdx]       = useState(3); // 1.0 default
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);

  const scale = ZOOM_STEPS[zoomIdx];

  // Jump to first target page when targetPages changes
  useEffect(() => {
    if (targetPages.length > 0) {
      setCurrentPage(targetPages[0]);
    }
  }, [targetPages.join(',')]);

  const onDocumentLoadSuccess = useCallback(({ numPages }) => {
    setNumPages(numPages);
    setLoading(false);
    setError(null);
  }, []);

  const onDocumentLoadError = useCallback((err) => {
    setError('Could not load document.');
    setLoading(false);
  }, []);

  const isTargetPage = targetPages.includes(currentPage);

  if (!fileUrl) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-muted-foreground">
        <FileText className="w-10 h-10 opacity-30" />
        <p className="text-sm">Select a source reference to view the document.</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-bg-deep rounded-lg border border-border overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost" size="icon" className="h-8 w-8"
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </Button>
          <span className="text-xs text-muted-foreground font-mono px-1 min-w-[60px] text-center">
            {currentPage} / {numPages ?? '—'}
          </span>
          <Button
            variant="ghost" size="icon" className="h-8 w-8"
            onClick={() => setCurrentPage(p => Math.min(numPages ?? p, p + 1))}
            disabled={!numPages || currentPage >= numPages}
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </Button>
        </div>

        <div className="flex items-center gap-1">
          {targetPages.length > 0 && (
            <div className="flex items-center gap-1 mr-2">
              {targetPages.slice(0, 4).map((pg) => (
                <button
                  key={pg}
                  onClick={() => setCurrentPage(pg)}
                  className={`text-[10px] font-mono px-1.5 py-0.5 rounded transition-colors ${
                    pg === currentPage
                      ? 'bg-warning/20 text-warning'
                      : 'bg-muted/30 text-muted-foreground hover:bg-muted/50'
                  }`}
                >
                  p.{pg}
                </button>
              ))}
            </div>
          )}
          <Button
            variant="ghost" size="icon" className="h-8 w-8"
            onClick={() => setZoomIdx(i => Math.max(0, i - 1))}
            disabled={zoomIdx === 0}
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </Button>
          <span className="text-xs text-muted-foreground font-mono w-9 text-center">
            {Math.round(scale * 100)}%
          </span>
          <Button
            variant="ghost" size="icon" className="h-8 w-8"
            onClick={() => setZoomIdx(i => Math.min(ZOOM_STEPS.length - 1, i + 1))}
            disabled={zoomIdx === ZOOM_STEPS.length - 1}
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </Button>
          {onToggleExpand && (
            <Button variant="ghost" size="icon" className="h-8 w-8 ml-1" onClick={onToggleExpand}>
              {isExpanded ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            </Button>
          )}
        </div>
      </div>

      {/* PDF canvas */}
      <div className="flex-1 overflow-auto flex justify-center py-4 px-2 relative">
        {isTargetPage && (
          <div
            className="absolute inset-x-2 top-4 pointer-events-none z-10"
            style={{ height: 'calc(100% - 32px)' }}
          >
            <div className="w-full h-full border-2 border-warning/50 rounded bg-warning/5" />
          </div>
        )}
        <Document
          file={fileUrl}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={onDocumentLoadError}
          loading={<PageSkeleton />}
        >
          <Page
            pageNumber={currentPage}
            scale={scale}
            renderTextLayer={true}
            renderAnnotationLayer={false}
            loading={<PageSkeleton />}
          />
        </Document>
        {error && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="w-[595px] h-[842px] bg-bg-elevated rounded animate-pulse" />
  );
}
