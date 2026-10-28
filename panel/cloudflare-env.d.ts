declare namespace Cloudflare {
  interface Env {
    DB?: D1Database;
    EVA_DEVELOPER_EMAILS?: string;
    BUCKET?: R2Bucket;
  }
}
