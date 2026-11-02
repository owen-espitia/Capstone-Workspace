import Image from "next/image";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col bg-paper">
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-10 px-8 py-16">
        <Image
          className="border border-ink"
          src="/weg.jpg"
          alt="SockCheck.ai"
          width={1000}
          height={100}
          priority
        />
        <div className="flex max-w-2xl flex-col gap-6">
          <p className="eyebrow text-brand">Outfit inspiration, on demand</p>
          <h1 className="text-6xl">
            Welcome to <span className="bg-accent px-2">SockCheck.ai</span>
          </h1>
          <p className="text-lg leading-8">
            The goal of this project is to give people the opportunity to get
            inspiration from a massive library of clothing combinations!
          </p>
          <p className="text-lg leading-8">
            Navigate to <i>Upload Image</i> to demo the project.
          </p>
        </div>
      </main>
    </div>
  );
}
