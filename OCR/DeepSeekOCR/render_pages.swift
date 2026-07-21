import Foundation
import PDFKit
import AppKit

func err(_ s: String) { FileHandle.standardError.write((s + "\n").data(using: .utf8)!) }

let args = CommandLine.arguments
guard args.count == 4, let dpi = Double(args[3]) else {
    err("usage: swift render_pages.swift <input.pdf> <outdir> <dpi>")
    exit(1)
}
guard let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
    err("cannot open \(args[1])")
    exit(2)
}
try? FileManager.default.createDirectory(atPath: args[2], withIntermediateDirectories: true)

let scale = CGFloat(dpi) / 72.0
for i in 0..<doc.pageCount {
    guard let page = doc.page(at: i) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let size = NSSize(width: bounds.width * scale, height: bounds.height * scale)
    let img = page.thumbnail(of: size, for: .mediaBox)
    guard let tiff = img.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff),
          let png = rep.representation(using: .png, properties: [:]) else {
        err("page \(i + 1): render failed")
        continue
    }
    let out = String(format: "%@/page-%03d.png", args[2], i + 1)
    try png.write(to: URL(fileURLWithPath: out))
}
err("rendered \(doc.pageCount) pages to \(args[2])")
