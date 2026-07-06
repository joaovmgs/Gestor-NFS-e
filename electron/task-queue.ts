export interface QueueSnapshot {
  processing: boolean;
  pending: number;
  activeId?: string;
  pendingIds: string[];
}

export class SequentialTaskQueue<T> {
  private readonly items: T[] = [];
  private processing = false;
  private activeItem: T | undefined;

  constructor(
    private readonly worker: (item: T) => Promise<void>,
    private readonly onChange: (snapshot: QueueSnapshot) => void = () => undefined,
    private readonly identify: (item: T) => string = () => ""
  ) {}

  enqueue(item: T): number {
    this.items.push(item);
    const position = this.items.length + (this.processing ? 1 : 0);
    this.emit();
    void this.drain();
    return position;
  }

  snapshot(): QueueSnapshot {
    return {
      processing: this.processing,
      pending: this.items.length,
      activeId: this.activeItem ? this.identify(this.activeItem) : undefined,
      pendingIds: this.items.map(this.identify)
    };
  }

  private async drain(): Promise<void> {
    if (this.processing) return;
    this.processing = true;
    this.emit();
    try {
      while (this.items.length > 0) {
        const item = this.items.shift();
        this.activeItem = item;
        this.emit();
        if (item !== undefined) {
          await this.worker(item);
        }
        this.activeItem = undefined;
      }
    } finally {
      this.processing = false;
      this.activeItem = undefined;
      this.emit();
    }
  }

  private emit(): void {
    this.onChange(this.snapshot());
  }
}
