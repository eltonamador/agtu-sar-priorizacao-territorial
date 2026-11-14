import Foundation
import ImageIO

func dictionary(_ value: Any?) -> [String: Any] {
    if let result = value as? [String: Any] {
        return result
    }
    if let source = value as? [AnyHashable: Any] {
        var result: [String: Any] = [:]
        for (key, item) in source {
            result[String(describing: key)] = item
        }
        return result
    }
    return [:]
}

func nullable(_ value: Any?) -> Any {
    value ?? NSNull()
}

func decimalCoordinate(_ gps: [String: Any], key: String, refKey: String) -> Double? {
    guard let number = gps[key] as? NSNumber else {
        return nil
    }
    let reference = (gps[refKey] as? String)?.uppercased() ?? ""
    let sign = (reference == "S" || reference == "W") ? -1.0 : 1.0
    return sign * number.doubleValue
}

func xmpValue(_ text: String, name: String) -> String? {
    let token = "drone-dji:\(name)=\""
    guard let start = text.range(of: token)?.upperBound,
          let end = text[start...].firstIndex(of: "\"") else {
        return nil
    }
    return String(text[start..<end])
}

var records: [[String: Any]] = []
for argument in CommandLine.arguments.dropFirst() {
    let fileURL = URL(fileURLWithPath: argument)
    guard let source = CGImageSourceCreateWithURL(fileURL as CFURL, nil),
          let rawProperties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) else {
        records.append([
            "file": fileURL.lastPathComponent,
            "error": "IMAGEIO_READ_FAILED"
        ])
        continue
    }

    let properties = dictionary(rawProperties)
    let exif = dictionary(properties["{Exif}"])
    let gps = dictionary(properties["{GPS}"])
    let tiff = dictionary(properties["{TIFF}"])
    let bytes = try Data(contentsOf: fileURL)
    let xmpText = String(decoding: bytes, as: UTF8.self)
    let attributes = try FileManager.default.attributesOfItem(atPath: argument)

    var record: [String: Any] = [
        "file": fileURL.lastPathComponent,
        "bytes": nullable(attributes[.size]),
        "uti": nullable(CGImageSourceGetType(source)),
        "width": nullable(properties["PixelWidth"]),
        "height": nullable(properties["PixelHeight"]),
        "orientation": nullable(properties["Orientation"]),
        "make": nullable(tiff["Make"]),
        "model": nullable(tiff["Model"]),
        "software": nullable(tiff["Software"]),
        "date_time_original": nullable(exif["DateTimeOriginal"]),
        "subsec_original": nullable(exif["SubsecTimeOriginal"]),
        "offset_original": nullable(exif["OffsetTimeOriginal"]),
        "latitude": nullable(decimalCoordinate(gps, key: "Latitude", refKey: "LatitudeRef")),
        "longitude": nullable(decimalCoordinate(gps, key: "Longitude", refKey: "LongitudeRef")),
        "altitude_m": nullable((gps["Altitude"] as? NSNumber)?.doubleValue),
        "horizontal_error_m": nullable((gps["HPositioningError"] as? NSNumber)?.doubleValue),
        "image_direction_deg_true": nullable((gps["ImgDirection"] as? NSNumber)?.doubleValue),
        "gps_date": nullable(gps["DateStamp"]),
        "gps_time_utc": nullable(gps["TimeStamp"]),
        "speed": nullable(gps["Speed"]),
        "speed_ref": nullable(gps["SpeedRef"]),
        "lens_model": nullable(exif["LensModel"]),
        "focal_length_mm": nullable(exif["FocalLength"]),
        "focal_length_35mm": nullable(exif["FocalLenIn35mmFilm"]),
        "f_number": nullable(exif["FNumber"]),
        "exposure_s": nullable(exif["ExposureTime"]),
        "iso": nullable((exif["ISOSpeedRatings"] as? [Any])?.first)
    ]

    for name in [
        "AbsoluteAltitude", "RelativeAltitude", "GimbalRollDegree",
        "GimbalYawDegree", "GimbalPitchDegree", "FlightRollDegree",
        "FlightYawDegree", "FlightPitchDegree"
    ] {
        record["dji_\(name)"] = nullable(xmpValue(xmpText, name: name))
    }
    records.append(record)
}

let output = try JSONSerialization.data(
    withJSONObject: records,
    options: [.sortedKeys]
)
FileHandle.standardOutput.write(output)
FileHandle.standardOutput.write(Data("\n".utf8))
