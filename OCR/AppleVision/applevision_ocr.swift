import Foundation
import PDFKit
import Vision
import AppKit

func err(_ s: String) { FileHandle.standardError.write((s + "\n").data(using: .utf8)!) }

let args = CommandLine.arguments
guard args.count == 3 else {
    err("usage: swift applevision_ocr.swift <input.pdf> <output.txt>")
    exit(1)
}
guard let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
    err("cannot open \(args[1])")
    exit(2)
}

var out = ""
let scale: CGFloat = 300.0 / 72.0

for i in 0..<doc.pageCount {
    guard let page = doc.page(at: i) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let size = NSSize(width: bounds.width * scale, height: bounds.height * scale)
    let img = page.thumbnail(of: size, for: .mediaBox)
    guard let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        err("page \(i + 1): render failed")
        continue
    }

    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["pl-PL"]
    req.usesLanguageCorrection = true

    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    } catch {
        err("page \(i + 1): OCR failed: \(error)")
        continue
    }

    // sort top-to-bottom, group observations sharing a baseline into one line
    let obs = (req.results ?? []).sorted { $0.boundingBox.midY > $1.boundingBox.midY }
    var lines: [[VNRecognizedTextObservation]] = []
    for o in obs {
        if var last = lines.last, let ref = last.first,
           abs(ref.boundingBox.midY - o.boundingBox.midY) < 0.008 {
            last.append(o)
            lines[lines.count - 1] = last
        } else {
            lines.append([o])
        }
    }
    let text = lines.map { line in
        line.sorted { $0.boundingBox.minX < $1.boundingBox.minX }
            .compactMap { $0.topCandidates(1).first?.string }
            .joined(separator: "\t")
    }.joined(separator: "\n")

    out += "--- page \(i + 1) ---\n" + text + "\n\n"
    err("page \(i + 1)/\(doc.pageCount) done (\(obs.count) observations)")
}

try out.write(toFile: args[2], atomically: true, encoding: .utf8)
err("wrote \(args[2])")
