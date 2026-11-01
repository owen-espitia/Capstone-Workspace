"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const previewUrlRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [limitReached, setLimitReached] = useState(false);
  const [requestsRemaining, setRequestsRemaining] = useState(null);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  function handleFileChange(event) {
    const selectedFile = event.target.files?.[0] ?? null;
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    const previewUrl = selectedFile ? URL.createObjectURL(selectedFile) : null;
    previewUrlRef.current = previewUrl;
    setFile(selectedFile);
    setPreview(previewUrl);
    setResult(null);
    setError(null);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!file || uploading) return;

    setUploading(true);
    setResult(null);
    setError(null);
    setLimitReached(false);

    const formData = new FormData();
    formData.append("image", file);

    try {
      const response = await fetch("/api/predict", {
        method: "POST",
        body: formData,
        credentials: "include",
      });
      const data = await response.json();

      if (response.status === 429) {
        setLimitReached(true);
        return;
      }

      if (!response.ok) {
        throw new Error(data.detail || "Image prediction failed.");
      }

      setResult(data);
      if (data.requests_remaining !== null && data.requests_remaining !== undefined) {
        setRequestsRemaining(data.requests_remaining);
      } else {
        setRequestsRemaining(null);
      }
    } catch (uploadError) {
      setError(
        uploadError instanceof Error
          ? uploadError.message
          : "Could not connect to the prediction service.",
      );
    } finally {
      setUploading(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 px-6 py-12">
      <div>
        <h1 className="text-3xl font-semibold">Find similar clothing</h1>
        <p className="mt-2 text-zinc-600">
          Choose a clothing image and we&apos;ll find similar catalog items.
        </p>
      </div>

      {limitReached ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-6 text-center">
          <p className="text-lg font-medium text-amber-900">Free request limit reached</p>
          <p className="mt-1 text-sm text-amber-700">
            You&apos;ve used your 2 free requests. Create a free account to keep going.
          </p>
          <div className="mt-4 flex justify-center gap-3">
            <Link
              href="/register"
              className="rounded-md bg-zinc-900 px-5 py-2 text-sm font-medium text-white hover:bg-zinc-700"
            >
              Create account
            </Link>
            <Link
              href="/login"
              className="rounded-md border border-zinc-300 px-5 py-2 text-sm font-medium hover:bg-zinc-100"
            >
              Sign in
            </Link>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label htmlFor="image-upload" className="font-medium">
            Image
          </label>
          <input
            id="image-upload"
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            className="block w-full rounded-md border border-zinc-300 p-3"
          />

          {preview && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={preview}
              alt="Selected upload preview"
              className="max-h-80 max-w-full self-start rounded-md object-contain"
            />
          )}

          {requestsRemaining !== null && (
            <p className="text-sm text-amber-600">
              {requestsRemaining === 0
                ? "This was your last free request. Sign up to continue."
                : `${requestsRemaining} free request${requestsRemaining === 1 ? "" : "s"} remaining.`}
              {" "}
              <Link href="/register" className="underline">
                Create a free account
              </Link>{" "}
              for unlimited access.
            </p>
          )}

          <button
            type="submit"
            disabled={!file || uploading}
            className="rounded-md bg-zinc-900 px-4 py-3 font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploading ? "Finding matches..." : "Find matches"}
          </button>
        </form>
      )}

      {error && (
        <p role="alert" className="rounded-md bg-red-50 p-3 text-red-700">
          {error}
        </p>
      )}

      {result && (
        <section aria-live="polite" className="flex flex-col gap-3">
          <h2 className="text-xl font-semibold">Results for {result.category}</h2>
          {result.matches.length === 0 ? (
            <p className="text-zinc-600">No matching catalog items found.</p>
          ) : (
            <ol className="flex flex-col gap-3">
              {result.matches.map((match) => (
                <li
                  key={match.image_id}
                  className="rounded-md border border-zinc-200 p-4"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={match.image_url}
                    alt={match.category}
                    className="mb-2 h-200 w-full rounded-md object-cover"
                  />
                  <p className="font-medium">{match.category}</p>
                  <p className="mt-1 text-sm">
                    Similarity: {(match.similarity * 100).toFixed(1)}%
                  </p>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </main>
  );
}
