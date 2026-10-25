'use client'
import Link from 'next/link';

export default function NavBar() {
    //Here is where we will need to implement login functionality
    return (
        <nav className="border-b border-zinc-200 bg-white dark:bg-zinc-950 dark:border-zinc-800">
            <div className='mx-auto flex max-w-4xl items-center gap-6 px-8 py-4'>
                <Link href='/' className='bg-cyan-950 border-2 border-solid rounded-md px-10'>
                    Home
                </Link>
                <Link href='/upload' className='bg-cyan-950 border-2 border-solid rounded-md px-10'>
                    Upload Image
                </Link>
            </div>
        </nav>
    );
}