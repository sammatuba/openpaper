"use client";

import { useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ProjectCanvas } from "@/components/project/canvas/ProjectCanvas";

// The project home is the canvas: the whole investigation on one surface.
// The case editor that used to live here is at /overview; a link saved to a
// claim on the old address is sent on to it.
export default function Page() {
    const { projectId } = useParams<{ projectId: string }>();
    const claim = useSearchParams().get("claim");
    const router = useRouter();
    useEffect(() => {
        if (claim) router.replace(`/projects/${projectId}/overview?claim=${encodeURIComponent(claim)}`);
    }, [claim, projectId, router]);
    if (claim) return null;
    return <div className="flex min-h-0 flex-1 flex-col"><ProjectCanvas /></div>;
}
