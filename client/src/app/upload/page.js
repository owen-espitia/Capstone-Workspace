"use client";
import { useEffect, useRef, useState } from "react";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const previewUrlRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
    };
  }, []);

  function handleFileChange(event) {
    const selectedFile = event.target.files?.[0] ?? null;
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
    }
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

    const formData = new FormData();
    formData.append("image", file);

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    try {
      const response = await fetch(`${apiUrl}/predict`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Image prediction failed.");
      }

      setResult(data);
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
 //NOTE: This page has been AI-generated as a proof of concept, flesh out later!
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 px-6 py-12">
      <div>
        <h1 className="text-3xl font-semibold">Find similar clothing</h1>
        <p className="mt-2 text-zinc-600">
          Choose a clothing image and we&apos;ll find similar catalog items.
        </p>
      </div>

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

        <button
          type="submit"
          disabled={!file || uploading}
          className="rounded-md bg-zinc-900 px-4 py-3 font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {uploading ? "Finding matches..." : "Find matches"}
        </button>
      </form>

      {error && (
        <p role="alert" className="rounded-md bg-red-50 p-3 text-red-700">
          {error}
        </p>
      )}

      {result && (
        <section aria-live="polite" className="flex flex-col gap-3">
          <h2 className="text-xl font-semibold">
            Results for {result.category}
          </h2>
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