"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const PAGE_SIZE = 24;
const FEEDBACK_MAX_CHARS = 2000; // matches the backend / DB limit

function formatDate(iso) {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

// Text feedback on one past inference: shows the saved note, or a form to write / edit it
function Feedback({ inferenceId, feedback, onChange, onUnauthorized }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(feedback?.text ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const fieldId = `feedback-${inferenceId}`;

  function startEditing() {
    setDraft(feedback?.text ?? "");
    setError(null);
    setEditing(true);
  }

  async function send(method, body) {
    setSaving(true);
    setError(null);
    try {
      const response = await fetch(`/api/history/${inferenceId}/feedback`, {
        method,
        credentials: "include",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (response.status === 401) {
        onUnauthorized();
        return null;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Could not save your feedback.");
      return data;
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Could not save your feedback.");
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) {
      setError("Feedback can't be empty.");
      return;
    }
    const data = await send("PUT", { feedback_text: text });
    if (data) {
      onChange(data.feedback);
      setEditing(false);
    }
  }

  async function handleRemove() {
    if (!window.confirm("Remove your feedback on this photo?")) return;
    const data = await send("DELETE");
    if (data) {
      onChange(null);
      setEditing(false);
    }
  }

  if (!editing) {
    return (
      <div className="mt-4 border-t border-hairline pt-3">
        {feedback ? (
          <div className="flex flex-col gap-2">
            <p className="label">Your feedback</p>
            <p className="whitespace-pre-wrap text-sm">{feedback.text}</p>
            <div className="flex gap-2">
              <button onClick={startEditing} className="btn btn-ghost">Edit</button>
              <button onClick={handleRemove} disabled={saving} className="btn btn-ghost">
                {saving ? "Removing..." : "Remove"}
              </button>
            </div>
          </div>
        ) : (
          <button onClick={startEditing} className="btn btn-ghost">Leave feedback</button>
        )}
        {error && <p role="alert" className="alert-error mt-2">{error}</p>}
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-2 border-t border-hairline pt-3">
      <label htmlFor={fieldId} className="label">
        How were these matches?
      </label>
      <textarea
        id={fieldId}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        maxLength={FEEDBACK_MAX_CHARS}
        rows={3}
        className="field"
        autoFocus
      />
      <p className="eyebrow self-end">
        {draft.length}/{FEEDBACK_MAX_CHARS}
      </p>
      {error && <p role="alert" className="alert-error">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={saving} className="btn btn-primary">
          {saving ? "Saving..." : "Save feedback"}
        </button>
        <button type="button" onClick={() => setEditing(false)} disabled={saving} className="btn btn-ghost">
          Cancel
        </button>
      </div>
    </form>
  );
}

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [uploadCount, setUploadCount] = useState(null);

  const loadPage = useCallback(
    async (offset) => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(
          `/api/history?limit=${PAGE_SIZE}&offset=${offset}`,
          { credentials: "include", cache: "no-store" },
        );
        if (response.status === 401) {
          router.replace("/login");
          return;
        }
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Could not load history.");
        setItems((prev) => (offset === 0 ? data.items : [...prev, ...data.items]));
        setHasMore(data.has_more);
        setUploadCount(data.upload_count ?? null);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load history.");
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  useEffect(() => {
    loadPage(0);
  }, [loadPage]);

  async function handleDelete(inferenceId) {
    if (!window.confirm("Delete this photo and its matches? This can't be undone.")) return;
    setDeletingId(inferenceId);
    setError(null);
    try {
      const response = await fetch(`/api/history/${inferenceId}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok && response.status !== 404) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Could not delete this item.");
      }
      setItems((prev) => prev.filter((item) => item.inference_id !== inferenceId));
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Could not delete this item.");
    } finally {
      setDeletingId(null);
    }
  }

  function handleFeedbackChange(inferenceId, feedback) {
    setItems((prev) =>
      prev.map((item) => (item.inference_id === inferenceId ? { ...item, feedback } : item)),
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-8 py-12">
      <div>
        <h1 className="text-5xl">Your wardrobe</h1>
        <p className="mt-3">
          Photos you&apos;ve uploaded before, with their closest catalog matches.
        </p>
        {uploadCount !== null && (
          <p className="eyebrow mt-2">
            {uploadCount} {uploadCount === 1 ? "upload" : "uploads"} so far
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="alert-error">
          {error}
        </p>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="border border-ink p-6">
          <p className="font-display text-2xl uppercase tracking-wider">Nothing here yet</p>
          <p className="mt-1 text-sm">Upload a clothing photo and it will be saved here.</p>
          <Link href="/upload" className="btn btn-primary mt-4">
            Upload image
          </Link>
        </div>
      )}

      <ul className="flex flex-col gap-6">
        {items.map((item) => (
          <li key={item.inference_id} className="border border-ink p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="eyebrow">{formatDate(item.created_at)}</p>
              <button
                onClick={() => handleDelete(item.inference_id)}
                disabled={deletingId === item.inference_id}
                className="btn btn-ghost"
              >
                {deletingId === item.inference_id ? "Deleting..." : "Delete"}
              </button>
            </div>
            <div className="grid gap-4 sm:grid-cols-4">
              <figure>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={item.image_url}
                  alt="Your upload"
                  className="aspect-square w-full border border-ink object-cover"
                />
                <figcaption className="eyebrow mt-1 text-brand">Your photo</figcaption>
              </figure>
              {item.matches.length === 0 ? (
                <p className="text-sm sm:col-span-3">No matches were stored for this photo.</p>
              ) : (
                item.matches.map((match, index) => (
                  <figure key={match.image_id}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={match.image_url}
                      alt={match.category}
                      className="aspect-square w-full border border-hairline object-cover"
                    />
                    <figcaption className="eyebrow mt-1">
                      #{index + 1} · {match.category} · {(match.similarity * 100).toFixed(1)}%
                    </figcaption>
                  </figure>
                ))
              )}
            </div>
            <Feedback
              inferenceId={item.inference_id}
              feedback={item.feedback}
              onChange={(feedback) => handleFeedbackChange(item.inference_id, feedback)}
              onUnauthorized={() => router.replace("/login")}
            />
          </li>
        ))}
      </ul>

      {loading && <p className="eyebrow">Loading...</p>}

      {hasMore && !loading && (
        <button onClick={() => loadPage(items.length)} className="btn btn-ghost self-start">
          Load more
        </button>
      )}
    </main>
  );
}
