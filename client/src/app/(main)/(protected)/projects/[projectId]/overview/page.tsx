"use client";

import { OverviewView } from "@/components/project/investigation/OverviewView";

// The investigation Overview (the case). The discussion starter and working
// brief live under /discuss; the project home is the canvas.
export default function Page() {
    return <div className="min-h-0 flex-1 overflow-y-auto"><OverviewView /></div>;
}
