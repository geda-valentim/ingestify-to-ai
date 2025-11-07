"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileText, Upload as UploadIcon, LogOut, Key, Search, Link as LinkIcon, Cloud } from "lucide-react";
import { useAuthStore } from "@/lib/store/auth";
import { jobsApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { FileUpload } from "@/components/upload/file-upload";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SourceType } from "@/types/api";

export default function DashboardPage() {
  const router = useRouter();
  const { user, clearAuth } = useAuthStore();
  const token = useAuthStore((state) => state.token);
  const isAuthenticated = useAuthStore((state) => state.token !== null && state.user !== null);
  const hasHydrated = useAuthStore((state) => state._hasHydrated);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [customName, setCustomName] = useState("");
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [urlSource, setUrlSource] = useState("");
  const [gdriveSource, setGdriveSource] = useState("");
  const [gdriveToken, setGdriveToken] = useState("");
  const [dropboxSource, setDropboxSource] = useState("");
  const [dropboxToken, setDropboxToken] = useState("");

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [isAuthenticated, hasHydrated, router]);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => jobsApi.upload(file, token!),
    onSuccess: (data) => {
      setUploadSuccess(data.job_id);
      // Clear all forms
      setSelectedFile(null);
      setCustomName("");
      setUrlSource("");
      setGdriveSource("");
      setGdriveToken("");
      setDropboxSource("");
      setDropboxToken("");
      // Redirect to job status page after 2 seconds
      setTimeout(() => {
        router.push(`/jobs/${data.job_id}`);
      }, 2000);
    },
  });

  const handleLogout = () => {
    clearAuth();
    router.push("/login");
  };

  const handleFileUpload = () => {
    if (!selectedFile) return;
    uploadMutation.mutate(selectedFile);
  };

  const handleUrlConvert = () => {
    if (!urlSource) return;
    // URL conversion not yet implemented in API
    alert("URL conversion coming soon!");
  };

  const handleGdriveConvert = () => {
    if (!gdriveSource || !gdriveToken) return;
    // Google Drive conversion not yet implemented in API
    alert("Google Drive conversion coming soon!");
  };

  const handleDropboxConvert = () => {
    if (!dropboxSource || !dropboxToken) return;
    // Dropbox conversion not yet implemented in API
    alert("Dropbox conversion coming soon!");
  };

  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted">
      {/* Header */}
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <FileText className="h-6 w-6 text-primary" />
              <h1 className="text-2xl font-bold">Doc2MD</h1>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-muted-foreground">
                Welcome, <span className="font-medium text-foreground">{user.username}</span>
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push("/api-keys")}
              >
                <Key className="h-4 w-4 mr-2" />
                API Keys
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push("/jobs")}
              >
                <Search className="h-4 w-4 mr-2" />
                My Jobs
              </Button>
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-12">
        <div className="max-w-3xl mx-auto space-y-8">
          {/* Conversion Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <FileText className="h-5 w-5" />
                <span>Convert Document</span>
              </CardTitle>
              <CardDescription>
                Choose your document source and convert it to Markdown format
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {uploadSuccess && (
                <div className="rounded-md bg-green-500/10 border border-green-500/20 p-4 text-sm text-green-600 dark:text-green-400">
                  <p className="font-medium">Conversion started!</p>
                  <p className="text-xs mt-1">Job ID: {uploadSuccess}</p>
                  <p className="text-xs mt-1">Redirecting to job status...</p>
                </div>
              )}

              {uploadMutation.isError && (
                <div className="rounded-md bg-destructive/10 border border-destructive/20 p-4 text-sm text-destructive">
                  Conversion failed. Please try again.
                </div>
              )}

              <Tabs defaultValue="file" className="w-full">
                <TabsList className="grid w-full grid-cols-4">
                  <TabsTrigger value="file">
                    <UploadIcon className="h-4 w-4 mr-2" />
                    File
                  </TabsTrigger>
                  <TabsTrigger value="url">
                    <LinkIcon className="h-4 w-4 mr-2" />
                    URL
                  </TabsTrigger>
                  <TabsTrigger value="gdrive">
                    <Cloud className="h-4 w-4 mr-2" />
                    Google Drive
                  </TabsTrigger>
                  <TabsTrigger value="dropbox">
                    <Cloud className="h-4 w-4 mr-2" />
                    Dropbox
                  </TabsTrigger>
                </TabsList>

                {/* File Upload Tab */}
                <TabsContent value="file" className="space-y-4 mt-4">
                  <FileUpload
                    onFileSelect={setSelectedFile}
                    selectedFile={selectedFile}
                    onClear={() => setSelectedFile(null)}
                  />

                  <div className="space-y-2">
                    <Label htmlFor="customNameFile">Custom Name (Optional)</Label>
                    <Input
                      id="customNameFile"
                      type="text"
                      placeholder="e.g., Monthly Report 2025"
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                    />
                  </div>

                  <Button
                    onClick={handleFileUpload}
                    disabled={!selectedFile || uploadMutation.isPending}
                    className="w-full"
                    size="lg"
                  >
                    {uploadMutation.isPending ? "Converting..." : "Convert to Markdown"}
                  </Button>
                </TabsContent>

                {/* URL Tab */}
                <TabsContent value="url" className="space-y-4 mt-4">
                  <div className="space-y-2">
                    <Label htmlFor="urlSource">Document URL</Label>
                    <Input
                      id="urlSource"
                      type="url"
                      placeholder="https://example.com/document.pdf"
                      value={urlSource}
                      onChange={(e) => setUrlSource(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      Enter a public URL to a document (PDF, DOCX, etc.)
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="customNameUrl">Custom Name (Optional)</Label>
                    <Input
                      id="customNameUrl"
                      type="text"
                      placeholder="e.g., Monthly Report 2025"
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                    />
                  </div>

                  <Button
                    onClick={handleUrlConvert}
                    disabled={!urlSource || uploadMutation.isPending}
                    className="w-full"
                    size="lg"
                  >
                    {uploadMutation.isPending ? "Converting..." : "Convert from URL"}
                  </Button>
                </TabsContent>

                {/* Google Drive Tab */}
                <TabsContent value="gdrive" className="space-y-4 mt-4">
                  <div className="space-y-2">
                    <Label htmlFor="gdriveSource">Google Drive File ID</Label>
                    <Input
                      id="gdriveSource"
                      type="text"
                      placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
                      value={gdriveSource}
                      onChange={(e) => setGdriveSource(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      The file ID from your Google Drive URL
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="gdriveToken">OAuth2 Token</Label>
                    <Input
                      id="gdriveToken"
                      type="password"
                      placeholder="ya29.a0AfH6SMB..."
                      value={gdriveToken}
                      onChange={(e) => setGdriveToken(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      Your Google OAuth2 access token
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="customNameGdrive">Custom Name (Optional)</Label>
                    <Input
                      id="customNameGdrive"
                      type="text"
                      placeholder="e.g., Monthly Report 2025"
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                    />
                  </div>

                  <Button
                    onClick={handleGdriveConvert}
                    disabled={!gdriveSource || !gdriveToken || uploadMutation.isPending}
                    className="w-full"
                    size="lg"
                  >
                    {uploadMutation.isPending ? "Converting..." : "Convert from Google Drive"}
                  </Button>
                </TabsContent>

                {/* Dropbox Tab */}
                <TabsContent value="dropbox" className="space-y-4 mt-4">
                  <div className="space-y-2">
                    <Label htmlFor="dropboxSource">Dropbox File Path</Label>
                    <Input
                      id="dropboxSource"
                      type="text"
                      placeholder="/documents/report.pdf"
                      value={dropboxSource}
                      onChange={(e) => setDropboxSource(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      The path to your file in Dropbox
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="dropboxToken">Access Token</Label>
                    <Input
                      id="dropboxToken"
                      type="password"
                      placeholder="sl.B1a2c3..."
                      value={dropboxToken}
                      onChange={(e) => setDropboxToken(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      Your Dropbox access token
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="customNameDropbox">Custom Name (Optional)</Label>
                    <Input
                      id="customNameDropbox"
                      type="text"
                      placeholder="e.g., Monthly Report 2025"
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                    />
                  </div>

                  <Button
                    onClick={handleDropboxConvert}
                    disabled={!dropboxSource || !dropboxToken || uploadMutation.isPending}
                    className="w-full"
                    size="lg"
                  >
                    {uploadMutation.isPending ? "Converting..." : "Convert from Dropbox"}
                  </Button>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          {/* Info Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Supported Formats</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="text-sm space-y-2 text-muted-foreground">
                  <li>• PDF Documents</li>
                  <li>• Microsoft Word (DOCX, DOC)</li>
                  <li>• HTML Files</li>
                  <li>• PowerPoint (PPTX)</li>
                  <li>• Excel (XLSX)</li>
                  <li>• Rich Text Format (RTF)</li>
                  <li>• OpenDocument Text (ODT)</li>
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">How It Works</CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="text-sm space-y-2 text-muted-foreground">
                  <li>1. Upload your document</li>
                  <li>2. Processing starts automatically</li>
                  <li>3. Track progress in real-time</li>
                  <li>4. Download Markdown output</li>
                  <li>5. Search and manage your jobs</li>
                </ol>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
