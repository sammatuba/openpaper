"use client";

import dynamic from "next/dynamic";
import type { PdfHighlighterViewerProps } from "./PdfHighlighterViewerClient";

export type { RenderedHighlightPosition } from "./PdfHighlighterViewerClient";
export type { ExtendedHighlight } from "./pdf-viewer/types";
export { paperHighlightToExtended, extendedToPaperHighlight } from "./pdf-viewer/types";

// PDF.js evaluates browser globals when imported. Keep the entire viewer module
// behind this boundary, including for server-rendered client components.
export const PdfHighlighterViewer = dynamic<PdfHighlighterViewerProps>(
    () => import("./PdfHighlighterViewerClient").then((mod) => mod.PdfHighlighterViewer),
    {
        ssr: false,
        loading: () => (
            <div role="status" className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Loading PDF viewer…
            </div>
        ),
    },
);
