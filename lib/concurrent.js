const MAX_CONCURRENT = 6;

export async function runConcurrent(tasks, concurrency = MAX_CONCURRENT) {
  const queue = [...tasks];
  const running = new Set();

  async function next() {
    while (queue.length > 0) {
      const task = queue.shift();
      const p = task().finally(() => running.delete(p));
      running.add(p);
      if (running.size >= concurrency) {
        await Promise.race(running);
      }
    }
  }

  await next();
  await Promise.allSettled(running);
}
