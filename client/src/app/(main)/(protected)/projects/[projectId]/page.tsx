"use client";

import { OverviewView } from "@/components/project/investigation/OverviewView";

// The project home is the investigation Overview (the case). The discussion
// starter and working brief live under /discuss.
export default function Page() {
    return <div className="min-h-0 flex-1 overflow-y-auto"><OverviewView /></div>;
}
