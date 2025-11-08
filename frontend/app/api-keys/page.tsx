"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Key,
  Plus,
  Copy,
  Trash2,
  CheckCircle2,
} from "lucide-react";
import { apiKeysApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatDistanceToNow } from "date-fns";

export default function ApiKeysPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = useAuthStore((state) => state.token);
  const isAuthenticated = useAuthStore((state) => state.token !== null && state.user !== null);
  const hasHydrated = useAuthStore((state) => state._hasHydrated);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [expiresInDays, setExpiresInDays] = useState<number>(30);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [isAuthenticated, hasHydrated, router]);

  const { data: apiKeys, isLoading } = useQuery({
    queryKey: ["api-keys", token],
    queryFn: () => apiKeysApi.list(),
    enabled: !!token,
  });

  const createMutation = useMutation({
    mutationFn: (data: { name: string }) => apiKeysApi.create(data),
    onSuccess: (data) => {
      setCreatedKey(data.api_key);
      setNewKeyName("");
      setExpiresInDays(30);
      setShowCreateForm(false);
      queryClient.invalidateQueries({ queryKey: ["api-keys", token] });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (id: string) => apiKeysApi.revoke(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-keys", token] });
    },
  });

  const handleCreateKey = () => {
    createMutation.mutate({
      name: newKeyName,
    });
  };

  const handleCopyKey = (key: string) => {
    navigator.clipboard.writeText(key);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
  };

  const handleRevokeKey = (keyId: string) => {
    if (confirm("Are you sure you want to revoke this API key? This action cannot be undone.")) {
      revokeMutation.mutate(keyId);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted">
      {/* Header */}
      <header className="border-b bg-background/95 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <Button variant="ghost" onClick={() => router.push("/dashboard")}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Dashboard
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-12">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold flex items-center gap-2">
                <Key className="h-8 w-8" />
                API Keys
              </h1>
              <p className="text-muted-foreground mt-1">
                Manage API keys for programmatic access
              </p>
            </div>
            <Button onClick={() => setShowCreateForm(!showCreateForm)}>
              <Plus className="h-4 w-4 mr-2" />
              Create API Key
            </Button>
          </div>

          {/* Created Key Alert */}
          {createdKey && (
            <Card className="border-green-500/50 bg-green-500/5">
              <CardHeader>
                <CardTitle className="text-green-600 dark:text-green-400 flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5" />
                  API Key Created Successfully
                </CardTitle>
                <CardDescription>
                  Make sure to copy your API key now. You won&apos;t be able to see it again!
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-2">
                  <Input
                    value={createdKey}
                    readOnly
                    className="font-mono text-sm"
                  />
                  <Button
                    onClick={() => handleCopyKey(createdKey)}
                    variant="outline"
                  >
                    {copiedKey ? (
                      <>
                        <CheckCircle2 className="h-4 w-4 mr-2" />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy className="h-4 w-4 mr-2" />
                        Copy
                      </>
                    )}
                  </Button>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCreatedKey(null)}
                >
                  I&apos;ve saved my API key
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Create Form */}
          {showCreateForm && (
            <Card>
              <CardHeader>
                <CardTitle>Create New API Key</CardTitle>
                <CardDescription>
                  API keys are used for programmatic access to the API
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="keyName">Key Name</Label>
                  <Input
                    id="keyName"
                    placeholder="e.g., Production Server"
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="expires">Expires In (days)</Label>
                  <Input
                    id="expires"
                    type="number"
                    min={1}
                    max={365}
                    value={expiresInDays}
                    onChange={(e) => setExpiresInDays(parseInt(e.target.value))}
                  />
                  <p className="text-xs text-muted-foreground">
                    Leave at 30 days or set to 365 for long-term keys
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={handleCreateKey}
                    disabled={!newKeyName || createMutation.isPending}
                  >
                    {createMutation.isPending ? "Creating..." : "Create Key"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setShowCreateForm(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* API Keys List */}
          <Card>
            <CardHeader>
              <CardTitle>Your API Keys</CardTitle>
              <CardDescription>
                {apiKeys?.length || 0} active API key(s)
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="text-center py-8 text-muted-foreground">
                  Loading...
                </div>
              ) : apiKeys && apiKeys.length > 0 ? (
                <div className="space-y-4">
                  {apiKeys.map((key) => (
                    <div
                      key={key.id}
                      className="flex items-center justify-between p-4 border rounded-lg"
                    >
                      <div className="flex-1">
                        <p className="font-medium">{key.name}</p>
                        <div className="flex gap-4 mt-1 text-sm text-muted-foreground">
                          <span>
                            Created {formatDistanceToNow(new Date(key.created_at), { addSuffix: true })}
                          </span>
                          {key.last_used_at && (
                            <span>
                              Last used {formatDistanceToNow(new Date(key.last_used_at), { addSuffix: true })}
                            </span>
                          )}
                          {key.expires_at && (
                            <span>
                              Expires {formatDistanceToNow(new Date(key.expires_at), { addSuffix: true })}
                            </span>
                          )}
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleRevokeKey(key.id)}
                        disabled={revokeMutation.isPending}
                        className="text-destructive hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <Key className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>No API keys yet</p>
                  <p className="text-sm mt-2">
                    Create one to start using the API programmatically
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Usage Info */}
          <Card>
            <CardHeader>
              <CardTitle>How to Use API Keys</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div>
                <p className="font-medium mb-2">Include the API key in your requests:</p>
                <pre className="bg-muted p-4 rounded-lg overflow-x-auto">
                  {`curl -X POST http://localhost:8080/upload \\
  -H "X-API-Key: doc2md_sk_..." \\
  -F "file=@document.pdf"`}
                </pre>
              </div>
              <div className="text-muted-foreground">
                <p>• API keys provide the same access as your user account</p>
                <p>• Keep your API keys secret and never commit them to version control</p>
                <p>• Revoke any keys that may have been compromised</p>
                <p>• Use different keys for different environments (dev, staging, prod)</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
