"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { platformSettingsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { formatApiError } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function PlatformSettingsPage() {
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);
  const queryKey = ["platform-settings", token];
  const settings = useQuery({ queryKey, queryFn: platformSettingsApi.get, enabled: !!token });
  const update = useMutation({
    mutationFn: platformSettingsApi.update,
    onMutate: () => setSaved(false),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKey, data);
      void queryClient.invalidateQueries({ queryKey: ["registration-settings"] });
      setSaved(true);
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Account registration</CardTitle>
        <CardDescription>Control whether visitors can create an account.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {settings.isPending ? <p role="status">Loading settings…</p> : settings.isError ? (
          <div className="space-y-3">
            <p role="alert" className="text-destructive">{formatApiError(settings.error)}</p>
            <Button variant="outline" onClick={() => void settings.refetch()}>Try again</Button>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between gap-4 rounded-lg border p-4">
              <div className="space-y-1">
                <p id="signup-label" className="font-medium">Allow signups</p>
                <p id="signup-description" className="text-sm text-muted-foreground">
                  {settings.data.signup_enabled ? "Anyone can create an account." : "New account registration is closed."}
                </p>
              </div>
              <Button
                role="switch"
                aria-checked={settings.data.signup_enabled}
                aria-labelledby="signup-label"
                aria-describedby="signup-description"
                variant={settings.data.signup_enabled ? "default" : "outline"}
                disabled={update.isPending}
                onClick={() => update.mutate({ signup_enabled: !settings.data.signup_enabled })}
              >
                {update.isPending ? "Saving…" : settings.data.signup_enabled ? "Enabled" : "Disabled"}
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">Changes apply immediately. Existing accounts can still sign in.</p>
          </>
        )}
        {update.isError && <p role="alert" className="text-sm text-destructive">{formatApiError(update.error)}</p>}
        {saved && <p role="status" className="text-sm">Settings saved.</p>}
      </CardContent>
    </Card>
  );
}
