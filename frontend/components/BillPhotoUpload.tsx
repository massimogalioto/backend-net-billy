"use client";
import { ChangeEvent, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Camera, Images, Plus, Trash2 } from "lucide-react";

const MAX_PHOTOS = 12;
const MAX_PHOTO_BYTES = 10 * 1024 * 1024;
const ACCEPTED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export default function BillPhotoUpload({ files, onChange, disabled = false }: {
  files: File[];
  onChange: (files: File[]) => void;
  disabled?: boolean;
}) {
  const cameraInput = useRef<HTMLInputElement>(null);
  const galleryInput = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  const [previews, setPreviews] = useState<string[]>([]);

  useEffect(() => {
    const urls = files.map(file => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach(url => URL.revokeObjectURL(url));
  }, [files]);

  function add(selected: File[]) {
    setError("");
    if (!selected.length) return;
    if (files.length + selected.length > MAX_PHOTOS) {
      setError(`Puoi caricare al massimo ${MAX_PHOTOS} fotografie.`);
      return;
    }
    const invalid = selected.find(file => !ACCEPTED_TYPES.has(file.type.toLowerCase()) || !file.size || file.size > MAX_PHOTO_BYTES);
    if (invalid) {
      setError("Usa immagini JPG, PNG o WEBP, fino a 10 MB ciascuna.");
      return;
    }
    onChange([...files, ...selected]);
  }

  function selected(event: ChangeEvent<HTMLInputElement>) {
    add(Array.from(event.target.files ?? []));
    event.target.value = "";
  }

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= files.length) return;
    const reordered = [...files];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
    onChange(reordered);
  }

  return <div className="photo-upload">
    <input ref={cameraInput} type="file" accept="image/*" capture="environment" onChange={selected} disabled={disabled} hidden aria-label="Scatta una foto della bolletta" />
    <input ref={galleryInput} type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" multiple onChange={selected} disabled={disabled} hidden aria-label="Seleziona fotografie della bolletta" />
    <div className="photo-actions">
      <button type="button" className="button outline" disabled={disabled || files.length >= MAX_PHOTOS} onClick={() => cameraInput.current?.click()}><Camera size={17} /> Scatta foto</button>
      <button type="button" className="button outline" disabled={disabled || files.length >= MAX_PHOTOS} onClick={() => galleryInput.current?.click()}>{files.length ? <Plus size={17} /> : <Images size={17} />} {files.length ? "Aggiungi pagine" : "Scegli dalla galleria"}</button>
    </div>
    {!files.length && <div className="photo-empty"><Images size={28} /><strong>Aggiungi le pagine nell’ordine corretto</strong><span>JPG, PNG o WEBP · massimo {MAX_PHOTOS} fotografie</span></div>}
    {!!files.length && <>
      <p className="photo-count" aria-live="polite">{files.length} {files.length === 1 ? "pagina selezionata" : "pagine selezionate"}</p>
      <ol className="photo-list">{files.map((file, index) => <li key={`${file.name}-${file.lastModified}-${index}`}>
        <img src={previews[index]} alt={`Anteprima pagina ${index + 1}`} />
        <div><strong>Pagina {index + 1}</strong><span>{file.name}</span></div>
        <div className="photo-order-actions">
          <button type="button" title="Sposta su" aria-label={`Sposta pagina ${index + 1} su`} disabled={disabled || index === 0} onClick={() => move(index, -1)}><ArrowUp size={16} /></button>
          <button type="button" title="Sposta giù" aria-label={`Sposta pagina ${index + 1} giù`} disabled={disabled || index === files.length - 1} onClick={() => move(index, 1)}><ArrowDown size={16} /></button>
          <button type="button" title="Elimina" aria-label={`Elimina pagina ${index + 1}`} disabled={disabled} onClick={() => onChange(files.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={16} /></button>
        </div>
      </li>)}</ol>
    </>}
    {error && <p className="alert error" role="alert">{error}</p>}
  </div>;
}
