export interface CatalogVolume {
  name: string;
  text_count: number;
  illus_count: number;
}

interface VolumeListProps {
  volumes: CatalogVolume[];
  selectedVolumes: string[];
  onToggle: (volumeName: string) => void;
}

export function VolumeList({
  volumes,
  selectedVolumes,
  onToggle,
}: VolumeListProps) {
  return (
    <section className="volume-index" aria-labelledby="volume-index-heading">
      <header className="workbench-section-heading volume-index-heading">
        <div>
          <p className="workbench-eyebrow">卷册索引</p>
          <h2 id="volume-index-heading">选择下载范围</h2>
        </div>
        <span className="workbench-count">
          {selectedVolumes.length}/{volumes.length}
        </span>
      </header>

      <ol className="volume-list">
        {volumes.map((volume, index) => (
          <li className="volume-row" key={volume.name}>
            <label>
              <input
                type="checkbox"
                checked={selectedVolumes.includes(volume.name)}
                onChange={() => onToggle(volume.name)}
              />
              <span className="volume-sequence">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="volume-copy">
                <strong>{volume.name}</strong>
                <span>
                  {volume.text_count} 章
                  {volume.illus_count > 0
                    ? ` · ${volume.illus_count} 个插图章节`
                    : ""}
                </span>
              </span>
            </label>
          </li>
        ))}
      </ol>
    </section>
  );
}
