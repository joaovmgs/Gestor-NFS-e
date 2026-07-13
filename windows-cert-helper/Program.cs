using System.Net;
using System.Security.Authentication;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

Console.InputEncoding = Encoding.UTF8;
Console.OutputEncoding = new UTF8Encoding(false);

if (args.Length == 0)
{
    Console.Error.WriteLine("Uso: Nfse.WindowsCertificates list | fetch <thumbprint> <nsu> [cnpjConsulta]");
    return 2;
}

if (string.Equals(args[0], "list", StringComparison.OrdinalIgnoreCase))
{
    Console.Write(JsonSerializer.Serialize(ListCertificates(), JsonOptions()));
    return 0;
}

if (string.Equals(args[0], "fetch", StringComparison.OrdinalIgnoreCase) && args.Length is 3 or 4)
{
    var certificate = FindCertificate(args[1]);
    if (certificate is null)
    {
        Console.Error.WriteLine("Certificado nao encontrado no repositorio do Windows.");
        return 3;
    }

    if (!long.TryParse(args[2], out var nsu) || nsu < 0)
    {
        Console.Error.WriteLine("NSU invalido.");
        return 4;
    }
    var cnpjConsulta = args.Length == 4 ? OnlyDigits(args[3]) : string.Empty;
    if (!string.IsNullOrEmpty(cnpjConsulta) && cnpjConsulta.Length != 14)
    {
        Console.Error.WriteLine("CNPJ de consulta invalido.");
        return 4;
    }

    using (certificate)
    using (var handler = new HttpClientHandler())
    {
        handler.ClientCertificateOptions = ClientCertificateOption.Manual;
        handler.ClientCertificates.Add(certificate);
        handler.SslProtocols = SslProtocols.Tls12;
        using var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(90) };
        client.DefaultRequestHeaders.Accept.ParseAdd("application/json");
        try
        {
            var query = string.IsNullOrEmpty(cnpjConsulta)
                ? "lote=true"
                : $"lote=true&cnpjConsulta={WebUtility.UrlEncode(cnpjConsulta)}";
            using var response = await client.GetAsync(
                $"https://adn.nfse.gov.br/contribuintes/DFe/{nsu}?{query}"
            );
            var body = await response.Content.ReadAsStringAsync();
            if (string.IsNullOrWhiteSpace(body))
            {
                Console.Error.WriteLine($"ADN retornou HTTP {(int)response.StatusCode} sem conteudo.");
                return 5;
            }
            Console.Write(body);
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"Falha na consulta ao ADN: {exception.Message}");
            return 6;
        }
    }
}

Console.Error.WriteLine("Comando invalido.");
return 2;

static object[] ListCertificates()
{
    var now = DateTimeOffset.Now;
    return ReadCertificates()
        .Where(certificate =>
            certificate.HasPrivateKey &&
            certificate.NotBefore <= now.LocalDateTime &&
            certificate.NotAfter >= now.LocalDateTime)
        .Select(certificate => new
        {
            thumbprint = certificate.Thumbprint,
            cnpj = ExtractCnpj(certificate),
            legalName = certificate.GetNameInfo(X509NameType.SimpleName, false),
            expiresAt = certificate.NotAfter.ToUniversalTime().ToString("O"),
            issuer = certificate.Issuer
        })
        .Where(certificate => certificate.cnpj.Length == 14)
        .GroupBy(certificate => certificate.thumbprint)
        .Select(group => (object)group.First())
        .OrderBy(certificate => certificate.ToString())
        .ToArray();
}

static X509Certificate2? FindCertificate(string thumbprint)
{
    var normalized = Regex.Replace(thumbprint, "[^0-9A-Fa-f]", "").ToUpperInvariant();
    return ReadCertificates().FirstOrDefault(
        certificate => string.Equals(certificate.Thumbprint, normalized, StringComparison.OrdinalIgnoreCase)
    );
}

static List<X509Certificate2> ReadCertificates()
{
    var certificates = new List<X509Certificate2>();
    foreach (var location in new[] { StoreLocation.CurrentUser, StoreLocation.LocalMachine })
    {
        using var store = new X509Store(StoreName.My, location);
        store.Open(OpenFlags.ReadOnly | OpenFlags.OpenExistingOnly);
        certificates.AddRange(store.Certificates);
    }
    return certificates;
}

static string ExtractCnpj(X509Certificate2 certificate)
{
    var candidates = new List<string> { certificate.Subject };
    foreach (var extension in certificate.Extensions)
    {
        if (extension.Oid?.Value == "2.5.29.17")
        {
            candidates.Add(Encoding.Latin1.GetString(extension.RawData));
            candidates.Add(extension.Format(false));
        }
    }

    foreach (var candidate in candidates)
    {
        var matches = Regex.Matches(candidate, @"(?<!\d)\d{14}(?!\d)");
        if (matches.Count > 0)
        {
            return matches[0].Value;
        }
    }
    return string.Empty;
}

static string OnlyDigits(string value) => Regex.Replace(value, @"\D", "");

static JsonSerializerOptions JsonOptions() => new()
{
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase
};
