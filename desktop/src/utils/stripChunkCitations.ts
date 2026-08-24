/** Remove inline RAG chunk ids the model sometimes echoes in prose. */
export function stripChunkCitations(text: string): string {
  return text.replace(/\s*\[Chunk\s+[^\]]+\]/gi, "");
}
